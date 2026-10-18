"""Deterministic diagnostics computed at startup or by the explicit evaluation CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike

from .artifacts import ArtifactError
from .modeling import baseline_metrics as calculate_baseline_metrics
from .modeling import calculate_metrics, rounded_metrics

if TYPE_CHECKING:
    from .service import ForecastService


def nullable_number(value: float) -> float | None:
    """Represent undefined descriptive statistics honestly in JSON."""
    return float(value) if np.isfinite(value) else None


def descriptive_statistics(series: pd.Series[Any]) -> dict[str, float | None]:
    values = {
        "mean": series.mean(),
        "std": series.std(),
        "median": series.median(),
        "min": series.min(),
        "max": series.max(),
        "q1": series.quantile(0.25),
        "q3": series.quantile(0.75),
    }
    return {name: nullable_number(round(value, 2)) for name, value in values.items()}


def metric_values(actual: ArrayLike, predicted: ArrayLike) -> dict[str, float | None]:
    return {
        name: nullable_number(value)
        for name, value in rounded_metrics(calculate_metrics(actual, predicted)).items()
    }


def baseline_metrics(frame: pd.DataFrame) -> dict[str, dict[str, float | None]]:
    return {
        name: {metric: nullable_number(value) for metric, value in rounded_metrics(values).items()}
        for name, values in calculate_baseline_metrics(frame).items()
    }


def performance(service: ForecastService) -> dict[str, Any]:
    val_data = (
        service.data.loc[service.test_start : service.package["test_period"]["end"]]
        .dropna(subset=["Demand"] + service.features)
        .copy()
    )
    X_val = val_data[service.features].dropna()
    y_val = val_data["Demand"].loc[X_val.index]
    y_pred = service.model.predict(X_val)

    metrics = metric_values(y_val, y_pred)

    errors = y_val.to_numpy(dtype=float) - y_pred

    # Downsample the actual-vs-predicted series for the chart (daily average)
    series_df = pd.DataFrame({"actual": y_val.values, "predicted": y_pred}, index=y_val.index)
    daily = series_df.resample("D").mean().dropna().round(2)

    top_features = sorted(
        service.package["feature_importance"].items(), key=lambda x: x[1], reverse=True
    )[:15]

    horizon_metrics = service.horizon_evaluation()
    return {
        "metrics": metrics,
        "test_period": service.package["test_period"],
        "early_stopping_period": service.package["early_stopping_period"],
        "baselines": baseline_metrics(val_data),
        "actual_vs_predicted": [
            {
                "date": str(cast(pd.Timestamp, idx).date()),
                "actual": row.actual,
                "predicted": row.predicted,
            }
            for idx, row in daily.iterrows()
        ],
        "error_histogram": np.histogram(errors, bins=40)[0].tolist(),
        "error_bin_edges": np.histogram(errors, bins=40)[1].round(1).tolist(),
        "feature_importance": [
            {"feature": f, "importance": round(float(v), 4)} for f, v in top_features
        ],
        "horizon_metrics": horizon_metrics,
    }


def horizons(service: ForecastService) -> dict[str, Any]:
    """Fixed 2024 sampled recursive backtest, separate from observed-lag scores."""
    results: dict[str, Any] = {"one_step_observed_lag": None, "recursive_multi_step": {}}
    val = service.data.loc[service.test_start : service.package["test_period"]["end"]].dropna(
        subset=["Demand", *service.features]
    )
    results["one_step_observed_lag"] = metric_values(
        val["Demand"], service.model.predict(val[service.features])
    )
    samples = []
    # Generate each origin once at 168h, then score prefixes for all horizons.
    for start in (
        pd.Timestamp(service.test_start) + pd.Timedelta(days=31),
        pd.Timestamp(service.test_start) + pd.Timedelta(days=213),
    ):
        if start + pd.Timedelta(hours=167) > service.data.index.max():
            continue
        rows = service.recursive_forecast(service.data.loc[service.data.index < start], start, 168)
        target = service.data.reindex(pd.date_range(start, periods=168, freq="h"))["Demand"]
        predictions = [r["predicted"] for r in rows]
        samples.append((target.tolist(), predictions))
    if not samples:
        raise ArtifactError("At least one complete recursive evaluation origin is required")
    for horizon in (1, 6, 24, 72, 168):
        actual, predicted = [], []
        for observations, forecasts in samples:
            for observed, estimate in zip(observations[:horizon], forecasts[:horizon]):
                if pd.notna(observed):
                    actual.append(observed)
                    predicted.append(estimate)
        results["recursive_multi_step"][str(horizon)] = {
            "origins": len(samples),
            "scored_rows": len(actual),
            "metrics": metric_values(actual, predicted)
            if actual
            else {name: None for name in ("mae", "rmse", "r2", "wape", "bias")},
            "weather": "historical_proxy",
        }
    return results
