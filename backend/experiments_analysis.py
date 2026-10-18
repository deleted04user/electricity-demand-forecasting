"""Causal historical diagnostics and portable research summaries."""

from __future__ import annotations

from typing import Any, cast

import numpy as np
import pandas as pd

from .experiments_protocol import Budget, metrics
from .features import add_engineered_features


def segmented_errors(
    frame: pd.DataFrame, predicted: np.ndarray, training_demand: pd.Series
) -> list[dict[str, Any]]:
    """Describe historical errors; demand bands are fixed by training quartiles."""
    if len(predicted) != len(frame):
        raise ValueError("Predictions and historical rows must match")
    values = frame[["Demand"]].copy()
    values["predicted"] = predicted
    quartiles = training_demand.quantile([0.25, 0.75])
    index = pd.DatetimeIndex(values.index)
    values["month"] = index.month
    values["hour"] = index.hour
    values["weekend"] = np.where(index.dayofweek >= 5, "weekend", "weekday")
    values["demand_band"] = np.where(
        values["Demand"] <= quartiles.iloc[0],
        "low",
        np.where(values["Demand"] > quartiles.iloc[1], "high", "middle"),
    )
    results = []
    for dimension in ("month", "hour", "weekend", "demand_band"):
        for label, group in values.groupby(dimension, observed=True):
            results.append(
                {
                    "dimension": dimension,
                    "segment": str(label),
                    "rows": len(group),
                    **metrics(group["Demand"], group["predicted"]),
                }
            )
    return results


def recursive_predictions(
    model: Any,
    features: tuple[str, ...],
    raw: pd.DataFrame,
    origin: pd.Timestamp,
    horizon: int,
    budget: Budget,
) -> np.ndarray:
    """Forecast with pre-origin observations and historical weather means only.

    At the first step the feature weather is the last observed hour. Subsequent
    steps use prior-step month/hour climatology estimated strictly before the
    origin. Future measured weather and future demand are never read.
    """
    available = raw.loc[raw.index < origin, ["Demand", "Temperature", "Humidity"]].copy()
    available = available.asfreq("h").ffill()
    required = pd.date_range(end=origin - pd.Timedelta(hours=1), periods=337, freq="h")
    if available.reindex(required).isna().any().any():
        raise ValueError("Recursive diagnostics require 337 complete pre-origin hours")
    if horizon < 1 or horizon > 168:
        raise ValueError("Diagnostic horizon must be in [1, 168]")
    available_index = pd.DatetimeIndex(available.index)
    seasonal = available.groupby([available_index.month, available_index.hour])[
        ["Temperature", "Humidity"]
    ].mean()
    hourly = available.groupby(available_index.hour)[["Temperature", "Humidity"]].mean()
    previous_weather = available[["Temperature", "Humidity"]].iloc[-1].to_numpy(dtype=float)
    history = available.tail(337).copy()
    history[["Temperature", "Humidity"]] = (
        available[["Temperature", "Humidity"]].shift(1).reindex(history.index)
    )
    predictions = []
    for stamp in pd.date_range(origin, periods=horizon, freq="h"):
        budget.check()
        history.loc[stamp] = [np.nan, *previous_weather]
        row = add_engineered_features(history).reindex(index=[stamp], columns=list(features))
        if not np.isfinite(row.to_numpy(dtype=float)).all():
            raise ValueError("Nonfinite recursive diagnostic features")
        prediction = float(model.predict(row)[0])
        if not np.isfinite(prediction) or prediction < 0:
            raise ValueError("Invalid recursive prediction")
        history.loc[stamp, "Demand"] = prediction
        history = history.tail(337)
        proxy = (
            seasonal.loc[(stamp.month, stamp.hour)]
            if (stamp.month, stamp.hour) in seasonal.index
            else hourly.loc[stamp.hour]
        )
        previous_weather = cast(pd.Series, proxy).to_numpy(dtype=float)
        if not np.isfinite(previous_weather).all():
            raise ValueError("Nonfinite historical weather proxy")
        predictions.append(prediction)
    return np.asarray(predictions)


def interval_diagnostics(
    model: Any,
    features: tuple[str, ...],
    raw: pd.DataFrame,
    absolute_calibration_residuals: np.ndarray,
    config: dict[str, Any],
    budget: Budget,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Evaluate the documented sqrt(h) interval heuristic at fixed monthly origins.

    Its radius comes only from 2023 out-of-fold one-step residuals. The 12
    per-horizon observations are descriptive, correlated and too few to certify
    nominal coverage. 2024 was previously evaluated in this repository.
    """
    residuals = np.asarray(absolute_calibration_residuals, dtype=float)
    if residuals.size == 0 or not np.isfinite(residuals).all() or (residuals < 0).any():
        raise ValueError("Finite, nonnegative calibration residuals are required")
    radius = float(np.quantile(residuals, config["nominal_coverage"], method="higher"))
    rows = []
    for month in range(1, 13):
        origin = pd.Timestamp(year=2024, month=month, day=1)
        predictions = recursive_predictions(model, features, raw, origin, 168, budget)
        for horizon in config["horizons"]:
            stamp = origin + pd.Timedelta(hours=horizon - 1)
            target = float(raw.reindex(index=[stamp])["Demand"].to_numpy(dtype=float)[0])
            # Missing measured demand is allowed by ingestion, never invented for scoring.
            actual = None if np.isnan(target) else target
            if actual is not None and (not np.isfinite(actual) or actual < 0):
                raise ValueError("Historical diagnostics require finite nonnegative targets")
            prediction = float(predictions[horizon - 1])
            spread = radius * np.sqrt(horizon)
            lower, upper = max(0.0, prediction - spread), prediction + spread
            rows.append(
                {
                    "origin": str(origin),
                    "timestamp": str(stamp),
                    "horizon_hours": horizon,
                    "actual": actual,
                    "predicted": prediction,
                    "lower": lower,
                    "upper": upper,
                    "covered": bool(lower <= actual <= upper) if actual is not None else None,
                    "target_available": actual is not None,
                    "width": upper - lower,
                }
            )
    summaries = []
    table = pd.DataFrame(rows)
    for horizon, group in table.groupby("horizon_hours"):
        scored = group.loc[group["target_available"]]
        values = (
            metrics(scored["actual"], scored["predicted"])
            if len(scored)
            else {name: None for name in ("mae", "rmse", "r2", "wape", "bias")}
        )
        summaries.append(
            {
                "horizon_hours": int(str(horizon)),
                "origins": len(scored),
                "planned_origins": len(group),
                "missing_target_origins": len(group) - len(scored),
                "nominal_coverage": config["nominal_coverage"],
                "empirical_coverage": float(scored["covered"].astype(bool).mean())
                if len(scored)
                else None,
                "mean_width_mw": float(group["width"].mean()),
                "calibration_radius_mw": radius,
                **values,
            }
        )
    return rows, summaries


def markdown_report(report: dict[str, Any]) -> str:
    """Generate the reviewable narrative directly from measured outputs."""
    rows = [
        "# Bounded synthetic research benchmark",
        "",
        "Research only. The bundled demand/weather workbook is synthetic. No model artifact is saved or promoted.",
        "",
        f"Run `{report['run_id']}`; generated {report['created_utc']}; elapsed {report['duration_seconds']:.2f}s; fits {report['fits_completed']}/28.",
        f"Git revision `{report['provenance']['git_revision']}`; dirty at execution: `{report['provenance']['git_dirty']}`. Exact source/config/data/lock hashes are in `report.json`.",
        "",
        "## Declared comparison",
        "",
        f"Three expanding 2023 folds use common timestamps and fixed {report['config']['parameters']['n_estimators']}-tree, depth-{report['config']['parameters']['max_depth']} XGBoost settings. One-step predictions use demand and weather observed through the preceding hour. Baselines use observed demand at lags 24 and 168. These are sequential one-step comparisons.",
        "",
        "| Variant | Seed | Folds | Mean fold WAPE (%) | Mean fold RMSE (MW) |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for result in report["comparisons"]:
        rows.append(
            f"| {result['variant']} | {result['seed']} | {result['folds']} | {result['mean_fold_wape']:.4f} | {result['mean_fold_rmse']:.2f} |"
        )
    rows += [
        "",
        f"The selected learned variant is **{report['selected_variant']}**, chosen exclusively by seed-42 mean 2023 fold WAPE, with RMSE as tie-breaker. Repeats 43/44 were predeclared for lags and full; their outcomes do not change selection.",
        "",
        "| Repeated variant | Seeds | Mean WAPE (%) | Population SD across seed means | Range (%) |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for result in report["seed_variability"]:
        rows.append(
            f"| {result['variant']} | 42,43,44 | {result['mean_wape']:.4f} | {result['std_wape']:.4f} | {result['min_wape']:.4f}–{result['max_wape']:.4f} |"
        )
    diagnostics = report["historical_diagnostics"]
    rows += [
        "",
        "## Reused historical 2024 diagnostics",
        "",
        "The repository already used 2024 in prior evaluation/promotion work. It is not an untouched final test. The chosen research variant is refit through 2023; 2024 diagnostics never select features or parameters.",
        "",
        f"Sequential one-step rows: {diagnostics['rows']}; WAPE: {diagnostics['metrics']['wape']:.4f}%; RMSE: {diagnostics['metrics']['rmse']:.2f} MW. `segmented_errors.csv` reports MAE/RMSE/WAPE/bias/R² and sample counts by month, hour, weekend and demand band. Demand-band boundaries come from training quartiles.",
        "",
        "## Interval coverage by recursive horizon",
        "",
        "Intervals use the 90th percentile of selected-variant 2023 out-of-fold absolute one-step errors, multiplied by sqrt(horizon). They are a heuristic, not horizon-calibrated conformal guarantees. Twelve predeclared monthly origins forecast recursively for 168 hours. Future weather is replaced by month/hour averages fitted strictly before each origin; future measured weather and demand are excluded.",
        "",
        "| Horizon (h) | Origins | Nominal coverage | Empirical coverage | Mean width (MW) | RMSE (MW) |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in diagnostics["intervals"]:
        coverage = (
            f"{100 * result['empirical_coverage']:.1f}%"
            if result["empirical_coverage"] is not None
            else "unavailable"
        )
        rmse = f"{result['rmse']:.2f}" if result["rmse"] is not None else "unavailable"
        rows.append(
            f"| {result['horizon_hours']} | {result['origins']}/{result['planned_origins']} | 90% | {coverage} | {result['mean_width_mw']:.2f} | {rmse} |"
        )
    under = [
        str(row["horizon_hours"])
        for row in diagnostics["intervals"]
        if row["empirical_coverage"] is not None and row["empirical_coverage"] < 0.9
    ]
    rows += [
        "",
        f"Observed undercoverage at horizons: {', '.join(under) if under else 'none in this small sample'}. Counts show scored/planned origins; unavailable actual demand is excluded without imputation. Wide intervals can cover most observations while providing little decision value. Twelve correlated origins have substantial sampling uncertainty; no coverage certification is implied.",
        "",
        "## Limitations and reproduction",
        "",
        "Synthetic data cannot establish operational forecasting accuracy, customer value or generalization to real Moroccan grid demand. Fixed small tree counts are a bounded feature study, not a production hyperparameter optimization. Correlated temporal folds and only three seeds limit inference. Sequential one-step and fixed-origin recursive results measure different tasks. A new independent real period is required before an unbiased final-performance claim.",
        "",
        "See `docs/EXPERIMENTS.md` for hash-locked installation and exact commands. `runs.csv` contains per-fold splits, feature lists, seeds, parameters, row hashes, fit durations and metrics. `report.json` is the portable source of this narrative. Timing, generated IDs, Git status and MLflow IDs may differ between reproductions; numeric metrics should match within the declared tolerance.",
        "",
    ]
    return "\n".join(rows)
