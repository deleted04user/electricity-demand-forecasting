"""Leakage-safe evaluation and bounded XGBoost training utility.

Run ``python -m backend.modeling --train`` from the project root. The 2024
holdout is not materialized or scored until configuration selection and final
training are complete. The active artifact is replaced only after a versioned
backup and only when candidate WAPE or RMSE is strictly better on common rows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from .features import IMPROVED_FEATURES, LEGACY_FEATURES, add_engineered_features
from .ingestion import load_hourly_data


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data/electricity_demand_2025.xlsx"
ACTIVE_MODEL_PATH = ROOT / "models/electricity_xgb_prediction_model.pkl"
TEST_START = pd.Timestamp("2024-01-01 00:00:00")
TEST_END = pd.Timestamp("2024-12-31 23:00:00")
SEED = 42
EARLY_STOPPING_ROUNDS = 50


@dataclass(frozen=True)
class Fold:
    name: str
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp


@dataclass(frozen=True)
class Candidate:
    name: str
    features: tuple[str, ...]
    params: dict


CURRENT_PARAMS = {
    "n_estimators": 1000,
    "learning_rate": 0.01,
    "max_depth": 6,
    "min_child_weight": 1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.0,
    "reg_lambda": 1.0,
}


def _params(**overrides) -> dict:
    params = dict(CURRENT_PARAMS)
    params.update(overrides)
    return params


# One benchmark plus seven focused candidates: 8 configs x 3 folds = 24 fits.
CANDIDATES = (
    Candidate("current_config_and_features", tuple(LEGACY_FEATURES), _params()),
    Candidate("enhanced_current_config", tuple(IMPROVED_FEATURES), _params()),
    Candidate("enhanced_depth4", tuple(IMPROVED_FEATURES), _params(n_estimators=1200, learning_rate=0.03, max_depth=4, min_child_weight=3, subsample=0.9, colsample_bytree=0.9, reg_lambda=2.0)),
    Candidate("enhanced_depth5", tuple(IMPROVED_FEATURES), _params(n_estimators=1200, learning_rate=0.03, max_depth=5, min_child_weight=3, subsample=0.9, colsample_bytree=0.9, reg_alpha=0.05, reg_lambda=2.0)),
    Candidate("enhanced_depth6", tuple(IMPROVED_FEATURES), _params(n_estimators=1400, learning_rate=0.02, max_depth=6, min_child_weight=3, subsample=0.9, colsample_bytree=0.9, reg_alpha=0.05, reg_lambda=2.0)),
    Candidate("enhanced_conservative", tuple(IMPROVED_FEATURES), _params(n_estimators=1400, learning_rate=0.02, max_depth=5, min_child_weight=5, subsample=0.85, colsample_bytree=0.85, reg_alpha=0.1, reg_lambda=3.0)),
    Candidate("enhanced_shallow", tuple(IMPROVED_FEATURES), _params(n_estimators=1200, learning_rate=0.04, max_depth=3, min_child_weight=3, subsample=0.9, colsample_bytree=0.9, reg_alpha=0.05, reg_lambda=2.0)),
    Candidate("enhanced_depth7", tuple(IMPROVED_FEATURES), _params(n_estimators=1200, learning_rate=0.02, max_depth=7, min_child_weight=5, subsample=0.85, colsample_bytree=0.85, reg_alpha=0.1, reg_lambda=3.0)),
)

ROLLING_FOLDS = (
    Fold("2023_jan_apr", pd.Timestamp("2022-12-31 23:00:00"), pd.Timestamp("2023-01-01"), pd.Timestamp("2023-04-30 23:00:00")),
    Fold("2023_may_aug", pd.Timestamp("2023-04-30 23:00:00"), pd.Timestamp("2023-05-01"), pd.Timestamp("2023-08-31 23:00:00")),
    Fold("2023_sep_dec", pd.Timestamp("2023-08-31 23:00:00"), pd.Timestamp("2023-09-01"), pd.Timestamp("2023-12-31 23:00:00")),
)

if len(CANDIDATES) > 12 or len(ROLLING_FOLDS) > 3:
    raise RuntimeError("Bounded-search contract exceeded")


def calculate_metrics(actual: Sequence[float], predicted: Sequence[float]) -> dict[str, float]:
    """Calculate all project metrics; bias is mean(prediction - actual)."""
    actual_array = np.asarray(actual, dtype=float)
    predicted_array = np.asarray(predicted, dtype=float)
    if actual_array.shape != predicted_array.shape or actual_array.size == 0:
        raise ValueError("actual and predicted must be non-empty arrays with identical shapes")
    if not (np.isfinite(actual_array).all() and np.isfinite(predicted_array).all()):
        raise ValueError("metrics require finite values")
    error = predicted_array - actual_array
    denominator = np.abs(actual_array).sum()
    if denominator == 0:
        raise ValueError("WAPE is undefined when absolute actual demand sums to zero")
    centered = actual_array - actual_array.mean()
    total_variation = np.square(centered).sum()
    return {
        "mae": float(np.abs(error).mean()),
        "rmse": float(np.sqrt(np.square(error).mean())),
        "r2": float(1 - np.square(error).sum() / total_variation) if total_variation else float("nan"),
        "wape": float(np.abs(error).sum() / denominator * 100),
        "bias": float(error.mean()),
    }


def rounded_metrics(metrics: dict[str, float]) -> dict[str, float]:
    return {name: round(value, 4 if name == "r2" else 2) for name, value in metrics.items()}


def chronological_splits(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return non-overlapping intended train/tuning/test periods."""
    return {
        "train": frame.loc[:"2022-12-31 23:00:00"],
        "tuning": frame.loc["2023-01-01":"2023-12-31 23:00:00"],
        "test": frame.loc[TEST_START:TEST_END],
    }


def rolling_origin_splits(frame: pd.DataFrame) -> list[tuple[Fold, pd.DataFrame, pd.DataFrame]]:
    folds = []
    for fold in ROLLING_FOLDS:
        train = frame.loc[:fold.train_end]
        validation = frame.loc[fold.validation_start:fold.validation_end]
        if train.empty or validation.empty or train.index.max() >= validation.index.min():
            raise ValueError(f"Invalid or empty rolling fold: {fold.name}")
        folds.append((fold, train, validation))
    return folds


def baseline_metrics(frame: pd.DataFrame) -> dict[str, dict[str, float]]:
    return {
        "24-hour naive": calculate_metrics(frame["Demand"], frame["demand_lag_24h"]),
        "168-hour naive": calculate_metrics(frame["Demand"], frame["demand_lag_168h"]),
    }


def _supervised(frame: pd.DataFrame, features: Iterable[str]) -> pd.DataFrame:
    columns = ["Demand", *features, "demand_lag_24h", "demand_lag_168h"]
    return frame.dropna(subset=list(dict.fromkeys(columns)))


def _xgb_model(params: dict, *, early_stopping: bool):
    try:
        from xgboost import XGBRegressor
    except ImportError as exc:
        raise RuntimeError("Training requires the existing project dependency 'xgboost'; no model was changed") from exc
    common = {"objective": "reg:squarederror", "random_state": SEED, "n_jobs": -1, "eval_metric": "rmse", **params}
    if early_stopping:
        common["early_stopping_rounds"] = EARLY_STOPPING_ROUNDS
    return XGBRegressor(**common)


def _average(metric_rows: list[dict[str, float]]) -> dict[str, float]:
    return {name: float(np.mean([row[name] for row in metric_rows])) for name in metric_rows[0]}


def select_configuration(data: pd.DataFrame) -> tuple[Candidate, list[dict]]:
    """Select by mean validation WAPE, breaking ties with mean RMSE."""
    results = []
    for candidate in CANDIDATES:
        fold_metrics = []
        fold_baselines = []
        for _, train_frame, validation_frame in rolling_origin_splits(data.loc[:"2023-12-31 23:00:00"]):
            train = _supervised(train_frame, candidate.features)
            validation = _supervised(validation_frame, candidate.features)
            model = _xgb_model(candidate.params, early_stopping=True)
            model.fit(train[list(candidate.features)], train["Demand"], eval_set=[(validation[list(candidate.features)], validation["Demand"])], verbose=False)
            fold_metrics.append(calculate_metrics(validation["Demand"], model.predict(validation[list(candidate.features)])))
            fold_baselines.append(baseline_metrics(validation))
        results.append({
            "name": candidate.name,
            "features": list(candidate.features),
            "params": candidate.params,
            "average_validation_metrics": _average(fold_metrics),
            "fold_metrics": fold_metrics,
            "average_naive_metrics": {name: _average([row[name] for row in fold_baselines]) for name in fold_baselines[0]},
        })
    winner_result = min(results, key=lambda row: (row["average_validation_metrics"]["wape"], row["average_validation_metrics"]["rmse"]))
    winner = next(candidate for candidate in CANDIDATES if candidate.name == winner_result["name"])
    return winner, results


def _fit_selected(data_before_test: pd.DataFrame, candidate: Candidate):
    train = _supervised(data_before_test.loc[:"2022-12-31 23:00:00"], candidate.features)
    tuning = _supervised(data_before_test.loc["2023-01-01":"2023-12-31 23:00:00"], candidate.features)
    selector = _xgb_model(candidate.params, early_stopping=True)
    selector.fit(train[list(candidate.features)], train["Demand"], eval_set=[(tuning[list(candidate.features)], tuning["Demand"])], verbose=False)
    best_rounds = int(getattr(selector, "best_iteration", candidate.params["n_estimators"] - 1)) + 1
    final_params = {**candidate.params, "n_estimators": best_rounds}
    combined = _supervised(data_before_test, candidate.features)
    final_model = _xgb_model(final_params, early_stopping=False)
    final_model.fit(combined[list(candidate.features)], combined["Demand"], verbose=False)
    return final_model, final_params


def _package_metrics(metrics: dict[str, float]) -> dict[str, float]:
    labels = {"mae": "MAE", "rmse": "RMSE", "r2": "R2", "wape": "WAPE", "bias": "Bias"}
    return {labels[name]: value for name, value in metrics.items()}


def run_training(data_path: Path | None = None) -> dict:
    """Run the one bounded pass and safely retain/promote its artifact."""
    try:
        import joblib
    except ImportError as exc:
        raise RuntimeError("Training requires the existing project dependency 'joblib'; no model was changed") from exc

    chosen_path = Path(data_path) if data_path else DATA_PATH
    if chosen_path == DATA_PATH:
        raise RuntimeError("Refusing to retrain on bundled synthetic data. Provide --data PATH to verified real local data.")
    raw = load_hourly_data(chosen_path)
    data = add_engineered_features(raw)

    # Selection and fitting see no 2024 rows.
    winner, validation_results = select_configuration(data.loc[:"2023-12-31 23:00:00"])
    final_model, final_params = _fit_selected(data.loc[:"2023-12-31 23:00:00"], winner)

    # Only now materialize one final common-row 2024 evaluation.
    old_package = joblib.load(ACTIVE_MODEL_PATH)
    old_features = tuple(old_package["features"])
    common_features = tuple(dict.fromkeys((*old_features, *winner.features)))
    test = _supervised(data.loc[TEST_START:TEST_END], common_features)
    old_metrics = calculate_metrics(test["Demand"], old_package["model"].predict(test[list(old_features)]))
    candidate_metrics = calculate_metrics(test["Demand"], final_model.predict(test[list(winner.features)]))
    naive_metrics = baseline_metrics(test)
    improved = candidate_metrics["wape"] < old_metrics["wape"] or candidate_metrics["rmse"] < old_metrics["rmse"]
    usable_training_start = _supervised(data.loc[:"2023-12-31 23:00:00"], winner.features).index.min()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate_dir = ROOT / "models/candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = candidate_dir / f"electricity_xgb_candidate_{timestamp}.pkl"
    package = {
        "model": final_model,
        "features": list(winner.features),
        "feature_importance": dict(zip(winner.features, map(float, final_model.feature_importances_))),
        "model_params": final_params,
        "training_date": datetime.now(timezone.utc).isoformat(),
        "training_period": {"start": str(usable_training_start), "end": "2023-12-31 23:00:00"},
        "early_stopping_period": {"start": "2023-01-01 00:00:00", "end": "2023-12-31 23:00:00"},
        "test_period": {"start": str(TEST_START), "end": str(TEST_END)},
        "metrics": _package_metrics(candidate_metrics),
        "baselines": {name: _package_metrics(values) for name, values in naive_metrics.items()},
        "selection": {"criterion": "mean rolling-validation WAPE; RMSE tie-breaker", "winner": winner.name},
        "data_filename": chosen_path.name,
        "data_sha256": hashlib.sha256(chosen_path.read_bytes()).hexdigest(),
        "synthetic_data": True,
    }
    joblib.dump(package, candidate_path)

    backup_path = None
    if improved:
        archive_dir = ROOT / "models/archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        backup_path = archive_dir / f"electricity_xgb_prediction_model_pre_{timestamp}.pkl"
        shutil.copy2(ACTIVE_MODEL_PATH, backup_path)
        temporary_active = ACTIVE_MODEL_PATH.with_name(ACTIVE_MODEL_PATH.name + ".tmp")
        shutil.copy2(candidate_path, temporary_active)
        os.replace(temporary_active, ACTIVE_MODEL_PATH)

    report = {
        "outcome": "improved_model_deployed" if improved else "candidate_retained",
        "candidate_path": str(candidate_path.relative_to(ROOT)),
        "backup_path": str(backup_path.relative_to(ROOT)) if backup_path else None,
        "selected_candidate": winner.name,
        "feature_list": list(winner.features),
        "model_params": final_params,
        "periods": {
            "training": {"start": str(usable_training_start), "end": "2023-12-31 23:00:00"},
            "tuning": {"start": "2023-01-01 00:00:00", "end": "2023-12-31 23:00:00"},
            "held_out_test": {"start": str(TEST_START), "end": str(TEST_END)},
        },
        "metrics": {"24-hour naive": naive_metrics["24-hour naive"], "168-hour naive": naive_metrics["168-hour naive"], "old XGBoost": old_metrics, "new XGBoost": candidate_metrics},
        "validation_results": validation_results,
        "data_filename": chosen_path.name,
        "data_sha256": hashlib.sha256(chosen_path.read_bytes()).hexdigest(),
        "test_rows": len(test),
        "synthetic_data": True,
    }
    report_path = candidate_dir / f"evaluation_{timestamp}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", action="store_true", help="run the bounded search and guarded artifact promotion")
    parser.add_argument("--data", type=Path, help="verified real local CSV/XLSX input; bundled synthetic data is refused")
    args = parser.parse_args()
    if not args.train:
        parser.error("No action requested; use --train")
    if not args.data:
        parser.error("--data is required; retraining cannot use bundled synthetic data")
    print(json.dumps(run_training(args.data), indent=2))


if __name__ == "__main__":
    main()
