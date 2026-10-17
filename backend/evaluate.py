"""Run from project root: python -m backend.evaluate [--manifest]. No training."""

import hashlib
import json
import sys
from typing import Any

import pandas as pd

from .ingestion import data_provenance
from .main import (
    DATA,
    DATA_PATH,
    FEATURES,
    MODEL_PACKAGE,
    MODEL_PATH,
    ROOT,
    metric_values,
    model_performance,
    recursive_forecast,
)


def latest_promotion_summary() -> dict[str, Any] | None:
    reports = list((ROOT / "models/candidates").glob("evaluation_*.json"))
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


def backtest() -> list[dict[str, Any]]:
    results = []
    for cutoff in ["2024-04-01", "2024-10-01"]:
        start = pd.Timestamp(cutoff)
        forecast = recursive_forecast(DATA.loc[DATA.index < start], start, 24)
        actual = DATA.loc[pd.date_range(start, periods=24, freq="h"), "Demand"]
        results.append(
            {
                "cutoff": cutoff,
                "horizon": 24,
                "weather": "historical_proxy",
                "metrics": metric_values(actual, [r["predicted"] for r in forecast]),
            }
        )
    return results


def manifest() -> dict[str, Any]:
    performance = model_performance()
    provenance = data_provenance(DATA_PATH, ROOT / "data/electricity_demand_2025.xlsx")
    usable_training = DATA.loc[: MODEL_PACKAGE["training_period"]["end"]].dropna(
        subset=["Demand", *FEATURES]
    )
    training_period = {
        **MODEL_PACKAGE["training_period"],
        "start": str(usable_training.index.min()),
    }
    payload = {
        "model_path": str(MODEL_PATH.relative_to(ROOT)),
        "version": MODEL_PACKAGE["training_date"],
        "features": FEATURES,
        "model_parameters": MODEL_PACKAGE.get("model_params", MODEL_PACKAGE["model"].get_params()),
        "data_filename": str(DATA_PATH.relative_to(ROOT))
        if DATA_PATH.is_relative_to(ROOT)
        else str(DATA_PATH),
        **provenance,
        "data_sha256": hashlib.sha256(DATA_PATH.read_bytes()).hexdigest(),
        "model_sha256": hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(),
        "training_period": training_period,
        "early_stopping_period": MODEL_PACKAGE["early_stopping_period"],
        "test_period": MODEL_PACKAGE["test_period"],
        "packaged_metrics": MODEL_PACKAGE["metrics"],
        "current_causal_test_metrics": performance["metrics"],
        "baselines": performance["baselines"],
        "promotion_evaluation": latest_promotion_summary(),
        "recursive_backtests": backtest(),
        "forecast_scope": "Best evaluated one-step-ahead/short-horizon. Recursive multi-step forecasts are experimental and accumulate error.",
        "note": (
            "Synthetic local demo. "
            if provenance["synthetic_data"]
            else "Caller-supplied local data; origin unverified. "
        )
        + "Fixed packaged model; backtests use no post-cutoff demand or weather.",
    }
    (ROOT / "models/metadata.json").write_text(json.dumps(payload, indent=2, default=float) + "\n")
    return payload


if __name__ == "__main__":
    print(
        json.dumps(manifest() if "--manifest" in sys.argv else backtest(), indent=2, default=float)
    )
