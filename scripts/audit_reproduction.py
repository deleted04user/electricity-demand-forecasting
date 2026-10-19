"""Independently audit bounded-study JSON/CSV/SQLite using only Python's stdlib."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
METRICS = ("mae", "rmse", "r2", "wape", "bias")
FILES = ("report.json", "runs.csv", "segmented_errors.csv", "interval_predictions.csv", "REPORT.md")
NUMERIC = {
    *METRICS,
    "train_rows",
    "validation_rows",
    "seed",
    "fit_seconds",
    "rows",
    "horizon_hours",
    "actual",
    "predicted",
    "lower",
    "upper",
    "width",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path, *, normalize_python: bool = False) -> str:
    content = path.read_bytes()
    if normalize_python and path.suffix == ".py":
        content = content.replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def close(actual: float, expected: float, tolerance: float) -> float:
    difference = abs(actual - expected)
    require(
        math.isfinite(difference) and difference <= tolerance,
        f"Metric differs: {actual} / {expected}",
    )
    return difference


def compare(actual: Any, expected: Any, tolerance: float) -> float:
    if isinstance(actual, bool) or isinstance(expected, bool):
        require(actual is expected, "Boolean fields differ")
        return 0.0
    if isinstance(actual, (float, int)) and isinstance(expected, (float, int)):
        return close(actual, expected, tolerance)
    if isinstance(actual, dict) and isinstance(expected, dict):
        require(actual.keys() == expected.keys(), "Report fields differ")
        return max((compare(actual[key], expected[key], tolerance) for key in actual), default=0.0)
    if isinstance(actual, list) and isinstance(expected, list):
        require(len(actual) == len(expected), "Row counts differ")
        return max(
            (compare(a, b, tolerance) for a, b in zip(actual, expected, strict=True)), default=0.0
        )
    require(actual == expected, f"Values differ: {actual!r} / {expected!r}")
    return 0.0


def table(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for key in row:
            value = row[key]
            if key in NUMERIC:
                row[key] = float(value) if value else None
            elif key in ("target_available", "covered"):
                require(value in ("True", "False", ""), f"Invalid boolean: {value!r}")
                row[key] = {"True": True, "False": False, "": None}[value]
    return rows


def mean(values: list[float]) -> float:
    return math.fsum(values) / len(values)


def metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    actual = [row["actual"] for row in rows]
    errors = [row["predicted"] - row["actual"] for row in rows]
    squared = math.fsum(value**2 for value in errors)
    total = math.fsum((value - mean(actual)) ** 2 for value in actual)
    return {
        "mae": mean([abs(value) for value in errors]),
        "rmse": math.sqrt(squared / len(rows)),
        "r2": 1 - squared / total,
        "wape": 100
        * math.fsum(abs(value) for value in errors)
        / math.fsum(abs(value) for value in actual),
        "bias": mean(errors),
    }


def check_tracking(
    folder: Path, report: dict[str, Any], runs: list[dict[str, Any]], *, required: bool
) -> int | None:
    tracking = report["tracking"]
    require(
        tracking["backend"] == "local_sqlite" and tracking["mlflow_executed"] is True,
        "Local tracking metadata missing",
    )
    mapping = {row["portable_run_id"]: row["mlflow_run_id"] for row in tracking["runs"]}
    require(set(mapping) == {row["run_id"] for row in runs}, "MLflow mappings differ")
    database_path = folder / "mlflow.db"
    require(database_path.is_file() or not required, f"Required local database missing: {folder}")
    if not database_path.is_file():
        return None
    tolerance = report["reproduction_tolerance"]["metric_absolute"]
    with sqlite3.connect(
        f"file:{database_path.resolve().as_posix()}?mode=ro", uri=True
    ) as database:
        stored = database.execute("SELECT run_uuid,name,status FROM runs").fetchall()
        require(
            len(stored) == 33
            and all(
                status == "FINISHED" and mapping.get(name) == uid for uid, name, status in stored
            ),
            "MLflow has incomplete or mismatched runs",
        )
        for row in runs:
            records = database.execute(
                "SELECT key,value,is_nan FROM metrics WHERE run_uuid=?", (mapping[row["run_id"]],)
            ).fetchall()
            require(
                len(records) == 6 and not any(nan for _, _, nan in records),
                "Invalid MLflow metrics",
            )
            compare(
                {key: value for key, value, _ in records},
                {key: row[key] for key in (*METRICS, "fit_seconds")},
                tolerance,
            )
    return len(stored)


def audit(
    folder: Path, *, current: bool = True, require_local_tracking: bool = False
) -> dict[str, Any]:
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    tolerance = report["reproduction_tolerance"]["metric_absolute"]
    require(tolerance == 0.0001, "Unexpected reproduction tolerance")
    provenance = report["provenance"]
    hashes = provenance["source_and_lock_sha256"]
    require(
        hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
        == provenance["source_manifest_sha256"],
        "Invalid source manifest",
    )
    if current:
        expected = {
            *ROOT.glob("backend/experiments*.py"),
            *(ROOT / f"backend/{name}.py" for name in ("features", "ingestion", "modeling")),
            *ROOT.glob("requirements*.lock.txt"),
            ROOT / "requirements-research.txt",
            ROOT / "pyproject.toml",
            ROOT / "uv.lock",
        }
        require(
            set(hashes) == {path.relative_to(ROOT).as_posix() for path in expected},
            "Missing source or native lock",
        )
        for name, digest in hashes.items():
            require(sha256(ROOT / name, normalize_python=True) == digest, f"Input changed: {name}")
        require(
            sha256(ROOT / provenance["data_path"]) == provenance["data_sha256"], "Dataset changed"
        )
        require(
            sha256(ROOT / "configs/experiments.json") == provenance["config_sha256"],
            "Protocol changed",
        )
        require(
            report["config"] == json.loads((ROOT / "configs/experiments.json").read_text()),
            "Recorded configuration differs from the frozen protocol",
        )
    model_hash = sha256(ROOT / "models/electricity_xgb_prediction_model.pkl")
    require(
        report["active_artifact_sha256_before"]
        == report["active_artifact_sha256_after"]
        == model_hash,
        "Active model changed",
    )
    require(
        report["fits_completed"] == 28 and report["provenance"]["production_promotion"] is False,
        "Unexpected fits or promotion",
    )
    runs = table(folder / "runs.csv")
    require(
        len(runs) == 33 and len({row["run_id"] for row in runs}) == 33,
        "Expected 33 distinct comparisons",
    )
    folds: dict[str, list[dict[str, Any]]] = defaultdict(list)
    groups: dict[tuple[str, float], list[dict[str, Any]]] = defaultdict(list)
    for row in runs:
        folds[row["fold"]].append(row)
        groups[row["variant"], row["seed"]].append(row)
    config = report["config"]
    expected_groups = {
        ("naive24", 42),
        ("naive168", 42),
        *((name, 42) for name in config["variants"]),
        *((name, seed) for name in config["repeat_variants"] for seed in config["repeat_seeds"]),
    }
    require(set(groups) == expected_groups, "Unexpected variant/seed comparisons")
    comparisons = report["comparisons"]
    require(
        len(comparisons) == len(expected_groups)
        and {(row["variant"], row["seed"]) for row in comparisons} == expected_groups,
        "Incomplete or duplicate comparison summaries",
    )
    require(
        len(report["seed_variability"]) == len(config["repeat_variants"])
        and {row["variant"] for row in report["seed_variability"]}
        == set(config["repeat_variants"]),
        "Incomplete or duplicate seed variability summaries",
    )
    require(set(folds) == set(report["config"]["folds"]), "Unexpected validation folds")
    for rows in folds.values():
        for key in (
            "train_start",
            "train_end",
            "validation_start",
            "validation_end",
            "train_rows",
            "validation_rows",
            "validation_timestamp_sha256",
        ):
            require(len({row[key] for row in rows}) == 1, f"Unmatched fold timestamps: {key}")
        require(
            len(rows) == 11 and rows[0]["train_end"] < rows[0]["validation_start"],
            "Overlapping train/validation split",
        )
        require(len(rows[0]["validation_timestamp_sha256"]) == 64, "Missing validation-row digest")
    for summary in report["comparisons"]:
        rows = groups[summary["variant"], summary["seed"]]
        require(
            len(rows) == summary["folds"] == 3
            and {row["fold"] for row in rows} == set(config["folds"]),
            "Incomplete fold comparison",
        )
        close(mean([row["wape"] for row in rows]), summary["mean_fold_wape"], tolerance)
        close(mean([row["rmse"] for row in rows]), summary["mean_fold_rmse"], tolerance)
    for variability in report["seed_variability"]:
        scores = [
            row["mean_fold_wape"]
            for row in report["comparisons"]
            if row["variant"] == variability["variant"]
        ]
        average = mean(scores)
        compare(
            {
                "mean_wape": average,
                "std_wape": math.sqrt(mean([(score - average) ** 2 for score in scores])),
                "min_wape": min(scores),
                "max_wape": max(scores),
            },
            {key: variability[key] for key in ("mean_wape", "std_wape", "min_wape", "max_wape")},
            tolerance,
        )
    eligible = [
        row
        for row in report["comparisons"]
        if row["seed"] == 42 and row["variant"] in report["config"]["variants"]
    ]
    selected = min(
        eligible, key=lambda row: (row["mean_fold_wape"], row["mean_fold_rmse"], row["variant"])
    )
    require(
        selected["variant"] == report["selected_variant"], "Selection differs from declared rule"
    )
    require(
        all(
            json.loads(row["features"]) == report["selected_features"]
            for row in runs
            if row["variant"] == report["selected_variant"]
        ),
        "Selected features differ from the comparison records",
    )
    segments = table(folder / "segmented_errors.csv")
    partitions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in segments:
        partitions[row["dimension"]].append(row)
    require(
        set(partitions) == {"month", "hour", "weekend", "demand_band"}, "Missing segment partition"
    )
    historical = report["historical_diagnostics"]
    for rows in partitions.values():
        require(sum(row["rows"] for row in rows) == historical["rows"], "Segment totals differ")
        require(len({row["segment"] for row in rows}) == len(rows), "Duplicate segment")
        for key in ("mae", "bias"):
            close(
                math.fsum(row["rows"] * row[key] for row in rows) / historical["rows"],
                historical["metrics"][key],
                tolerance,
            )
        close(
            math.sqrt(
                math.fsum(row["rows"] * row["rmse"] ** 2 for row in rows) / historical["rows"]
            ),
            historical["metrics"]["rmse"],
            tolerance,
        )
    intervals = table(folder / "interval_predictions.csv")
    counts = []
    horizons = set(config["historical_diagnostics"]["horizons"])
    require(
        len(historical["intervals"]) == len(horizons)
        and {row["horizon_hours"] for row in historical["intervals"]} == horizons
        and {row["horizon_hours"] for row in intervals} == horizons,
        "Incomplete or duplicate interval horizons",
    )
    for summary in historical["intervals"]:
        rows = [row for row in intervals if row["horizon_hours"] == summary["horizon_hours"]]
        scored = [row for row in rows if row["target_available"]]
        require(
            len(rows) == summary["planned_origins"] == 12 and len(scored) == summary["origins"],
            "Origin counts differ",
        )
        require(
            {row["origin"] for row in rows}
            == {f"2024-{month:02d}-01 00:00:00" for month in range(1, 13)},
            "Expected distinct predeclared monthly origins",
        )
        require(
            len(rows) - len(scored) == summary["missing_target_origins"],
            "Missing actuals were counted",
        )
        for row in rows:
            require(
                datetime.fromisoformat(row["timestamp"])
                == datetime.fromisoformat(row["origin"])
                + timedelta(hours=row["horizon_hours"] - 1),
                "Invalid recursive timestamp",
            )
            require(
                row["target_available"] is (row["actual"] is not None),
                "Invalid target availability",
            )
            expected_coverage = (
                row["lower"] <= row["actual"] <= row["upper"] if row["target_available"] else None
            )
            require(row["covered"] is expected_coverage, "Invalid coverage boolean")
            close(row["upper"] - row["lower"], row["width"], tolerance)
        covered = sum(row["covered"] is True for row in scored)
        close(covered / len(scored), summary["empirical_coverage"], tolerance)
        close(mean([row["width"] for row in rows]), summary["mean_width_mw"], tolerance)
        compare(metrics(scored), {key: summary[key] for key in METRICS}, tolerance)
        counts.append(
            {
                "horizon_hours": summary["horizon_hours"],
                "covered": covered,
                "scored_origins": len(scored),
                "planned_origins": len(rows),
                "coverage": covered / len(scored),
            }
        )
    require(len(intervals) == 60, "Unexpected interval rows")
    return {
        "report": report,
        "runs": runs,
        "segments": segments,
        "intervals": intervals,
        "interval_counts": counts,
        "database_count": check_tracking(folder, report, runs, required=require_local_tracking),
    }


def comparison(first: dict[str, Any], second: dict[str, Any], tolerance: float) -> float:
    keys = (
        "config",
        "fits_completed",
        "selected_variant",
        "selected_features",
        "comparisons",
        "seed_variability",
        "historical_diagnostics",
    )
    differences = [
        compare(
            {key: first["report"][key] for key in keys},
            {key: second["report"][key] for key in keys},
            tolerance,
        )
    ]
    for record in (first, second):
        require(
            record["report"]["final_research_refit"]["seed"] == 42, "Unexpected final refit seed"
        )
    differences.append(
        compare(
            {
                key: value
                for key, value in first["report"]["final_research_refit"].items()
                if key != "fit_seconds"
            },
            {
                key: value
                for key, value in second["report"]["final_research_refit"].items()
                if key != "fit_seconds"
            },
            tolerance,
        )
    )
    versions = ("numpy", "pandas", "xgboost", "holidays")
    require(
        {key: first["report"]["environment"][key] for key in versions}
        == {key: second["report"]["environment"][key] for key in versions},
        "Scientific runtime package versions differ",
    )

    def clean(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {key: value for key, value in row.items() if key not in ("run_id", "fit_seconds")}
            for row in rows
        ]

    for name in ("runs", "segments", "intervals"):
        differences.append(compare(clean(first[name]), clean(second[name]), tolerance))
    return max(differences)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path)
    parser.add_argument("repeat", type=Path)
    parser.add_argument("--historical", type=Path)
    parser.add_argument(
        "--require-local-tracking",
        action="store_true",
        help="Require both studies' ignored SQLite databases; otherwise check them when present",
    )
    parser.add_argument(
        "--output", type=Path, help="Create a new proof file; existing files are preserved"
    )
    args = parser.parse_args()
    require(
        args.first.resolve() != args.repeat.resolve(), "Reproduction needs distinct study folders"
    )
    first = audit(args.first, require_local_tracking=args.require_local_tracking)
    repeated = audit(args.repeat, require_local_tracking=args.require_local_tracking)
    require(
        first["report"]["run_id"] != repeated["report"]["run_id"],
        "Reproduction needs independently generated study run IDs",
    )
    first_ids = {row["mlflow_run_id"] for row in first["report"]["tracking"]["runs"]}
    repeated_ids = {row["mlflow_run_id"] for row in repeated["report"]["tracking"]["runs"]}
    require(first_ids.isdisjoint(repeated_ids), "Reproduction needs independent MLflow run IDs")
    tolerance = first["report"]["reproduction_tolerance"]["metric_absolute"]
    maximum = comparison(first, repeated, tolerance)
    require(
        first["report"]["provenance"]["source_manifest_sha256"]
        == repeated["report"]["provenance"]["source_manifest_sha256"],
        "Study inputs differ",
    )
    proof = {
        "status": "passed",
        "method": "independent stdlib JSON/csv/math/sqlite3 checks; no pandas or MLflow imports",
        "runs": [
            {
                "path": folder.resolve().relative_to(ROOT).as_posix(),
                "run_id": record["report"]["run_id"],
                "report_sha256": sha256(folder / "report.json"),
                "portable_files_sha256": {name: sha256(folder / name) for name in FILES},
            }
            for folder, record in ((args.first, first), (args.repeat, repeated))
        ],
        "source_manifest_sha256": first["report"]["provenance"]["source_manifest_sha256"],
        "tolerance_absolute": tolerance,
        "maximum_metric_difference": maximum,
        "independent_interval_counts": first["interval_counts"],
        "common_fold_timestamp_checks": "passed",
        "segment_partition_counts": "passed",
        "csv_metric_checks": "passed",
        "sqlite_metrics_checks": "passed"
        if first["database_count"] and repeated["database_count"]
        else "not_checked_missing_local_database",
        "native_lock_and_current_input_hashes": "passed",
        "active_artifact_unchanged": True,
        "mlflow_local_database_finished_runs": [
            first["database_count"],
            repeated["database_count"],
        ],
    }
    if args.historical:
        prior = audit(args.historical, current=False)
        names = (
            "backend/experiments.py",
            "backend/experiments_analysis.py",
            "backend/features.py",
            "backend/ingestion.py",
            "backend/modeling.py",
        )
        unchanged = all(
            first["report"]["provenance"]["source_and_lock_sha256"][name]
            == prior["report"]["provenance"]["source_and_lock_sha256"][name]
            for name in names
        )
        proof["historical_run_comparison"] = {
            "path": args.historical.resolve().relative_to(ROOT).as_posix(),
            "report_sha256": sha256(args.historical / "report.json"),
            "maximum_metric_difference": comparison(first, prior, tolerance),
            "scientific_prediction_source_hashes_unchanged": unchanged,
            "note": "Native lock adoption, optional error-reporting dependency and expanded provenance; predictive code/config and resolved scientific package versions retained",
        }
    content = json.dumps(proof, indent=2, allow_nan=False) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        print(f"Independent reproduction audit passed; wrote {args.output}")
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
