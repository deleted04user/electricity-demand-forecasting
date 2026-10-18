"""Explicit evaluation entry point: python -m backend.evaluate [--manifest|--diagnostics]."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pandas as pd

from .artifacts import file_sha256
from .diagnostics import metric_values
from .ingestion import data_provenance
from .service import ForecastService
from .settings import Settings


@contextmanager
def _loaded(service: ForecastService | None) -> Iterator[ForecastService]:
    owned = service is None
    active = ForecastService.load(Settings.from_env()) if service is None else service
    try:
        yield active
    finally:
        if owned:
            active.close()


def latest_promotion_summary(root: Path | None = None) -> dict[str, Any] | None:
    base = Settings.from_env().root if root is None else root
    reports = list((base / "models/candidates").glob("evaluation_*.json"))
    if not reports:
        return None
    report = json.loads(
        max(reports, key=lambda path: path.stat().st_mtime).read_text(encoding="utf-8")
    )
    selected = next(
        row for row in report["validation_results"] if row["name"] == report["selected_candidate"]
    )
    return {
        "outcome": report["outcome"],
        "selected_candidate": report["selected_candidate"],
        "candidate_path": report["candidate_path"],
        "backup_path": report["backup_path"],
        "test_rows": report["test_rows"],
        "selection_criterion": "lowest mean rolling-origin validation WAPE; RMSE tie-breaker",
        "rolling_validation_metrics": selected["average_validation_metrics"],
        "held_out_comparison": report["metrics"],
    }


def backtest(service: ForecastService | None = None) -> list[dict[str, Any]]:
    with _loaded(service) as active:
        results = []
        for cutoff in ["2024-04-01", "2024-10-01"]:
            start = pd.Timestamp(cutoff)
            forecast = active.recursive_forecast(
                active.data.loc[active.data.index < start], start, 24
            )
            actual = active.data.reindex(pd.date_range(start, periods=24, freq="h"))["Demand"]
            results.append(
                {
                    "cutoff": cutoff,
                    "horizon": 24,
                    "weather": "historical_proxy",
                    "metrics": metric_values(actual, [row["predicted"] for row in forecast]),
                }
            )
        return results


def manifest(service: ForecastService | None = None) -> dict[str, Any]:
    with _loaded(service) as active:
        settings = active.settings
        if file_sha256(settings.data_path) != active.data_sha256:
            raise ValueError(
                "Evaluation data changed after service initialization; reload before evaluation"
            )
        package = active.package
        performance = active.model_performance()
        provenance = data_provenance(settings.data_path, settings.bundled_data_path)
        payload = {
            "model_path": settings.model_path.relative_to(settings.root).as_posix(),
            "version": package["training_date"],
            "features": active.features,
            "model_parameters": package.get("model_params", active.model.get_params()),
            "data_filename": settings.data_path.relative_to(settings.root).as_posix()
            if settings.data_path.is_relative_to(settings.root)
            else str(settings.data_path),
            **provenance,
            "data_sha256": active.data_sha256,
            "model_sha256": active.model_sha256,
            "diagnostics_identity": active.identity,
            "training_period": package["training_period"],
            "evaluation_data_coverage": {
                "start": str(active.data.index.min()),
                "end": str(active.data.index.max()),
            },
            "early_stopping_period": package["early_stopping_period"],
            "test_period": package["test_period"],
            "packaged_metrics": package["metrics"],
            "current_causal_test_metrics": performance["metrics"],
            "baselines": performance["baselines"],
            "promotion_evaluation": latest_promotion_summary(settings.root),
            "recursive_backtests": backtest(active),
            "forecast_scope": "Best evaluated one-step-ahead/short-horizon. Recursive multi-step forecasts are experimental and accumulate error.",
            "note": (
                "Synthetic local demo. "
                if provenance["synthetic_data"]
                else "Caller-supplied local data; origin unverified. "
            )
            + "Fixed packaged model; backtests use no post-cutoff demand or weather.",
        }
        if file_sha256(settings.data_path) != active.data_sha256:
            raise ValueError("Evaluation data changed while evaluating; no manifest was written")
        (settings.root / "models/metadata.json").write_text(
            json.dumps(payload, indent=2, default=float, allow_nan=False) + "\n", encoding="utf-8"
        )
        return payload


def main() -> None:
    if "--diagnostics" in sys.argv:
        with _loaded(None) as active:
            active.write_diagnostics()
            print(
                json.dumps(
                    {
                        "diagnostics_path": str(active.settings.diagnostics_path),
                        "identity": active.identity,
                    }
                )
            )
    else:
        print(
            json.dumps(
                manifest() if "--manifest" in sys.argv else backtest(),
                indent=2,
                default=float,
                allow_nan=False,
            )
        )


if __name__ == "__main__":
    main()
