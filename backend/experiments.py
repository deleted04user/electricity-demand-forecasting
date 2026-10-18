"""Bounded offline research CLI; never imports serving or writes a model.

Run ``python -m backend.experiments --output experiments/reports/my-run``.
The supervisor kills its worker at the configured wall-clock limit. JSON/CSV
reports are always portable; optional MLflow uses only a local SQLite store.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .experiments_analysis import interval_diagnostics, markdown_report, segmented_errors
from .experiments_protocol import (
    DATA_PATH,
    DEFAULT_CONFIG,
    FEATURE_GROUPS,
    ROOT,
    Budget,
    causal_frame,
    load_config,
    metrics,
    prepare_output,
    provenance,
    sha256,
    verify_provenance,
)
from .ingestion import load_hourly_data
from .modeling import ROLLING_FOLDS, rolling_origin_splits


def _row_hash(frame: pd.DataFrame) -> str:
    import hashlib

    return hashlib.sha256(
        frame.index.to_numpy(dtype="datetime64[ns]").astype("<i8").tobytes()
    ).hexdigest()


def _fit(
    train: pd.DataFrame,
    features: tuple[str, ...],
    seed: int,
    config: dict[str, Any],
    budget: Budget,
) -> tuple[Any, float]:
    from xgboost import XGBRegressor

    budget.check(fit=True)
    model = XGBRegressor(
        **config["parameters"],
        objective="reg:squarederror",
        random_state=seed,
        n_jobs=config["budget"]["threads"],
        tree_method="hist",
        eval_metric="rmse",
    )
    start = time.monotonic()
    model.fit(train[list(features)], train["Demand"])
    budget.check()
    return model, time.monotonic() - start


def _comparisons(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = pd.DataFrame(runs).groupby(["variant", "seed"], sort=True)
    return [
        {
            "variant": variant,
            "seed": int(str(seed)),
            "folds": len(group),
            "mean_fold_wape": float(group["wape"].mean()),
            "mean_fold_rmse": float(group["rmse"].mean()),
        }
        for (variant, seed), group in grouped
    ]


def select_variant(comparisons: list[dict[str, Any]]) -> str:
    """Selection sees only initial-seed learned-variant 2023 validation rows."""
    eligible = [
        row for row in comparisons if row["seed"] == 42 and row["variant"] in FEATURE_GROUPS
    ]
    if len(eligible) != len(FEATURE_GROUPS) or any(
        not np.isfinite([row["mean_fold_wape"], row["mean_fold_rmse"]]).all() for row in eligible
    ):
        raise ValueError("All finite seed42 variant comparisons are required")
    return str(
        min(
            eligible, key=lambda row: (row["mean_fold_wape"], row["mean_fold_rmse"], row["variant"])
        )["variant"]
    )


def _versions() -> dict[str, str]:
    result = {"python": platform.python_version(), "platform": platform.platform()}
    for package in ("numpy", "pandas", "xgboost", "holidays", "mlflow-skinny"):
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = "not installed (optional)"
    return result


def _local_tracking(
    output: Path, report: dict[str, Any], runs: list[dict[str, Any]]
) -> dict[str, Any]:
    """An explicit local SQLite URI ignores inherited remote tracking settings."""
    os.environ["MLFLOW_DISABLE_TELEMETRY"] = "true"
    os.environ["MLFLOW_ENABLE_OTLP_EXPORTER"] = "false"
    try:
        mlflow = importlib.import_module("mlflow")
    except ImportError as exc:
        raise RuntimeError(
            "--mlflow requires the optional requirements-research.lock.txt installation"
        ) from exc
    database = (output / "mlflow.db").resolve()
    mlflow.set_tracking_uri(f"sqlite:///{database.as_posix()}")
    existing = mlflow.get_experiment_by_name("bounded-synthetic-research")
    experiment_id = (
        existing.experiment_id
        if existing
        else mlflow.create_experiment(
            "bounded-synthetic-research", artifact_location=(output / "mlflow_artifacts").as_uri()
        )
    )
    mlflow.set_experiment(experiment_id=experiment_id)
    mlflow_ids = []
    for row in runs:
        with mlflow.start_run(run_name=row["run_id"]) as active:
            mlflow.log_params(
                {
                    name: row[name]
                    for name in ("variant", "seed", "fold", "train_rows", "validation_rows")
                }
            )
            if row["variant"] in FEATURE_GROUPS:
                mlflow.log_params(report["config"]["parameters"])
            mlflow.log_metrics(
                {name: row[name] for name in ("mae", "rmse", "wape", "bias", "fit_seconds")}
            )
            if row["r2"] is not None:
                mlflow.log_metric("r2", row["r2"])
            mlflow.set_tags(
                {
                    "git_revision": str(report["provenance"]["git_revision"]),
                    "git_dirty": str(report["provenance"]["git_dirty"]),
                    "data_sha256": report["provenance"]["data_sha256"],
                    "config_sha256": report["provenance"]["config_sha256"],
                    "research_only": "true",
                    "synthetic": "true",
                }
            )
            mlflow.log_dict(
                {"row": row, "provenance": report["provenance"]}, "portable_provenance.json"
            )
            mlflow_ids.append(
                {"portable_run_id": row["run_id"], "mlflow_run_id": active.info.run_id}
            )
    return {
        "backend": "local_sqlite",
        "database": "mlflow.db",
        "experiment_id": experiment_id,
        "runs": mlflow_ids,
    }


def run_experiment(config_path: Path, output: Path, *, tracking: bool = False) -> dict[str, Any]:
    """Worker entry; output was newly prepared by the bounded supervisor."""
    started = time.monotonic()
    config = load_config(config_path)
    budget = Budget(
        **{name: config["budget"][name] for name in ("max_fits", "max_seconds")}, started=started
    )
    if tracking:
        # Validate optional imports and the local database before spending any fits.
        _local_tracking(output, {}, [])
        budget.check()
    active_path = ROOT / "models/electricity_xgb_prediction_model.pkl"
    artifact_before = sha256(active_path)
    source = provenance(config_path)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    raw = load_hourly_data(DATA_PATH)
    common = causal_frame(raw.loc[:"2023-12-31 23:00:00"])
    budget.check()
    folds = rolling_origin_splits(common.loc[:"2023-12-31 23:00:00"])
    if tuple(fold.name for fold, _, _ in folds) != tuple(fold.name for fold in ROLLING_FOLDS):
        raise ValueError("Unexpected validation folds")
    runs: list[dict[str, Any]] = []
    residuals: dict[str, list[np.ndarray]] = {variant: [] for variant in FEATURE_GROUPS}
    for fold, train, validation in folds:
        base = {
            "fold": fold.name,
            "train_start": str(train.index.min()),
            "train_end": str(train.index.max()),
            "validation_start": str(validation.index.min()),
            "validation_end": str(validation.index.max()),
            "train_rows": len(train),
            "validation_rows": len(validation),
            "validation_timestamp_sha256": _row_hash(validation),
        }
        for name, column in (("naive24", "demand_lag_24h"), ("naive168", "demand_lag_168h")):
            runs.append(
                {
                    **base,
                    "run_id": f"{run_id}_{fold.name}_{name}_42",
                    "variant": name,
                    "seed": 42,
                    "features": [column],
                    "fit_seconds": 0.0,
                    **metrics(validation["Demand"], validation[column]),
                }
            )
        declared = [(name, 42) for name in config["variants"]] + [
            (name, seed) for seed in config["repeat_seeds"] for name in config["repeat_variants"]
        ]
        for name, seed in declared:
            features = FEATURE_GROUPS[name]
            model, duration = _fit(train, features, seed, config, budget)
            predicted = model.predict(validation[list(features)])
            values = metrics(validation["Demand"], predicted)
            runs.append(
                {
                    **base,
                    "run_id": f"{run_id}_{fold.name}_{name}_{seed}",
                    "variant": name,
                    "seed": seed,
                    "features": list(features),
                    "fit_seconds": duration,
                    **values,
                }
            )
            if seed == 42:
                residuals[name].append(np.abs(validation["Demand"].to_numpy() - predicted))
    comparisons = _comparisons(runs)
    selected = select_variant(comparisons)
    features = FEATURE_GROUPS[selected]
    training = common.loc[:"2023-12-31 23:00:00"]
    # 2024 targets are materialized only after feature selection and final fit.
    model, final_fit_seconds = _fit(training, features, 42, config, budget)
    historical = causal_frame(raw).loc["2024-01-01":"2024-12-31 23:00:00"]
    if historical.empty:
        raise ValueError("Historical 2024 diagnostics are unavailable")
    predicted = model.predict(historical[list(features)])
    segments = segmented_errors(historical, predicted, training["Demand"])
    interval_rows, intervals = interval_diagnostics(
        model,
        features,
        raw,
        np.concatenate(residuals[selected]),
        config["historical_diagnostics"],
        budget,
    )
    repeated = []
    for name in config["repeat_variants"]:
        scores = np.array([row["mean_fold_wape"] for row in comparisons if row["variant"] == name])
        repeated.append(
            {
                "variant": name,
                "mean_wape": float(scores.mean()),
                "std_wape": float(scores.std()),
                "min_wape": float(scores.min()),
                "max_wape": float(scores.max()),
            }
        )
    artifact_after = sha256(active_path)
    if artifact_before != artifact_after:
        raise RuntimeError("Active model changed during experiment; refusing success report")
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "created_utc": datetime.now(UTC).isoformat(),
        "provenance": source,
        "environment": _versions(),
        "config": config,
        "active_artifact_sha256_before": artifact_before,
        "active_artifact_sha256_after": artifact_after,
        "fits_completed": budget.fits,
        "selected_variant": selected,
        "selected_features": list(features),
        "comparisons": comparisons,
        "seed_variability": repeated,
        "final_research_refit": {
            "seed": 42,
            "training_start": str(training.index.min()),
            "training_end": str(training.index.max()),
            "rows": len(training),
            "fit_seconds": final_fit_seconds,
        },
        "historical_diagnostics": {
            "status": "reused_historical_2024_not_untouched_test",
            "rows": len(historical),
            "metrics": metrics(historical["Demand"], predicted),
            "intervals": intervals,
            "demand_band_quartiles_mw": training["Demand"].quantile([0.25, 0.75]).tolist(),
        },
        "reproduction_tolerance": {
            "metric_absolute": 0.0001,
            "note": "same locked packages and CPU architecture; timing, IDs and provenance differ",
        },
        "tracking": {"backend": "portable_json_csv", "mlflow_executed": False},
    }
    if tracking:
        report["tracking"] = {**_local_tracking(output, report, runs), "mlflow_executed": True}
    verify_provenance(source, config_path)
    budget.check()
    report["duration_seconds"] = time.monotonic() - started
    csv_runs = [
        {
            **row,
            "features": json.dumps(row["features"]),
            "parameters": json.dumps(
                config["parameters"] if row["variant"] in FEATURE_GROUPS else {}, sort_keys=True
            ),
        }
        for row in runs
    ]
    pd.DataFrame(csv_runs).to_csv(output / "runs.csv", index=False, float_format="%.10g")
    pd.DataFrame(segments).to_csv(
        output / "segmented_errors.csv", index=False, float_format="%.10g"
    )
    pd.DataFrame(interval_rows).to_csv(
        output / "interval_predictions.csv", index=False, float_format="%.10g"
    )
    (output / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    (output / "REPORT.md").write_text(markdown_report(report), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--output", type=Path, required=True, help="New child folder of experiments/reports"
    )
    parser.add_argument(
        "--mlflow", action="store_true", help="Also log locally with optional research dependencies"
    )
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.worker:
        # This path is private to the supervisor; do not allow writes outside reports.
        if not args.output.resolve().is_relative_to((ROOT / "experiments/reports").resolve()):
            raise ValueError("Worker output outside experiment reports")
        report = run_experiment(args.config, args.output, tracking=args.mlflow)
        print(
            json.dumps(
                {
                    "run_id": report["run_id"],
                    "fits": report["fits_completed"],
                    "seconds": report["duration_seconds"],
                    "selected": report["selected_variant"],
                }
            )
        )
        return 0
    output = prepare_output(args.output)
    command = [
        sys.executable,
        "-m",
        "backend.experiments",
        "--worker",
        "--config",
        str(args.config.resolve()),
        "--output",
        str(output),
    ]
    if args.mlflow:
        command.append("--mlflow")
    environment = {
        **os.environ,
        "OMP_NUM_THREADS": str(config["budget"]["threads"]),
        "OPENBLAS_NUM_THREADS": str(config["budget"]["threads"]),
        "MKL_NUM_THREADS": str(config["budget"]["threads"]),
        "MLFLOW_ENABLE_SYSTEM_METRICS_LOGGING": "false",
        "MLFLOW_DISABLE_TELEMETRY": "true",
        "MLFLOW_DISABLE_AGENT_HINT": "1",
        "MLFLOW_ENABLE_OTLP_EXPORTER": "false",
    }
    try:
        completed = subprocess.run(
            command, cwd=ROOT, env=environment, timeout=config["budget"]["max_seconds"], check=False
        )
    except subprocess.TimeoutExpired:
        print(
            "Research runtime limit reached; no model was promoted and no successful report was written.",
            file=sys.stderr,
        )
        return 124
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
