"""Shared, causal hourly feature engineering for training and inference.

All demand-derived features use observations strictly before the feature row.
Weather is forward-filled only; leading missing weather remains unavailable.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Collection

import numpy as np
import pandas as pd

try:
    from holidays import country_holidays
except ImportError:  # Lets dependency-light unit tests inject an empty holiday set.
    country_holidays = None


DEMAND_LAGS = (1, 2, 3, 6, 12, 24, 48, 72, 168, 336)
ROLLING_WINDOWS = (6, 24, 168)

# Exact schema used by the currently packaged model.
LEGACY_FEATURES = (
    "hour", "dayofweek", "month", "year", "dayofyear", "quarter", "weekofyear",
    "Temperature", "Humidity", "is_holiday", "is_weekend", "Demand_lag_24hr",
    "demand_lag_168hr", "demand_rolling_mean_24hr", "demand_rolling_std_24hr",
)

# Feature order is part of the candidate model contract and is stored in its package.
IMPROVED_FEATURES = (
    "hour", "dayofweek", "month", "year", "dayofyear", "quarter", "weekofyear",
    "hour_sin", "hour_cos", "dayofweek_sin", "dayofweek_cos", "is_weekend",
    "is_holiday", "Temperature", "Humidity", "temperature_squared",
    *(f"demand_lag_{lag}h" for lag in DEMAND_LAGS),
    *(f"demand_rolling_{stat}_{window}h" for window in ROLLING_WINDOWS for stat in ("mean", "std")),
)


@lru_cache(maxsize=16)
def _morocco_holiday_dates(years: tuple[int, ...]) -> frozenset:
    if country_holidays is None:
        raise RuntimeError("The 'holidays' package is required when holiday_dates is not supplied")
    return frozenset(country_holidays("MA", years=years).keys())


def add_engineered_features(
    df: pd.DataFrame,
    *,
    holiday_dates: Collection | None = None,
) -> pd.DataFrame:
    """Return an hourly frame with leakage-safe calendar, weather and demand features.

    ``holiday_dates`` is injectable for deterministic, dependency-light tests. Normal
    application calls use the installed ``holidays`` package for Moroccan holidays.
    Ramadan is intentionally omitted because no reliable existing local dependency
    in this project supplies it.
    """
    data = df.copy().dropna(how="all")

    if "Timestamp" in data.columns:
        data["Timestamp"] = pd.to_datetime(data["Timestamp"])
        data = data.set_index("Timestamp")
    if not isinstance(data.index, pd.DatetimeIndex):
        raise TypeError("Feature engineering requires a DatetimeIndex or Timestamp column")

    data = data.sort_index()
    if data.index.has_duplicates:
        raise ValueError("Duplicate hourly timestamps")
    data = data.asfreq("h")

    required = {"Demand", "Temperature", "Humidity"}
    missing = sorted(required.difference(data.columns))
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    # Deliberately no bfill/interpolation: a row can only see prior weather.
    data["Temperature"] = data["Temperature"].ffill()
    data["Humidity"] = data["Humidity"].ffill()
    # Demand targets remain missing. Carry-forward is confined to historical inputs.
    demand_history = data["Demand"].ffill()

    data["hour"] = data.index.hour
    data["dayofweek"] = data.index.dayofweek
    data["month"] = data.index.month
    data["year"] = data.index.year
    data["dayofyear"] = data.index.dayofyear
    data["quarter"] = data.index.quarter
    data["weekofyear"] = data.index.isocalendar().week.astype(int)
    data["is_weekend"] = data.index.dayofweek.isin([5, 6]).astype("int32")

    hour_angle = 2 * np.pi * data["hour"] / 24.0
    weekday_angle = 2 * np.pi * data["dayofweek"] / 7.0
    data["hour_sin"] = np.sin(hour_angle)
    data["hour_cos"] = np.cos(hour_angle)
    data["dayofweek_sin"] = np.sin(weekday_angle)
    data["dayofweek_cos"] = np.cos(weekday_angle)

    if holiday_dates is None:
        years = tuple(range(data.index.min().year, data.index.max().year + 1))
        holiday_dates = _morocco_holiday_dates(years)
    holiday_dates = set(holiday_dates)
    data["is_holiday"] = data.index.map(lambda stamp: int(stamp.date() in holiday_dates)).astype("int32")

    data["temperature_squared"] = data["Temperature"] ** 2

    for lag in DEMAND_LAGS:
        data[f"demand_lag_{lag}h"] = demand_history.shift(lag)

    past_demand = demand_history.shift(1)
    for window in ROLLING_WINDOWS:
        rolling = past_demand.rolling(window=window, min_periods=window)
        data[f"demand_rolling_mean_{window}h"] = rolling.mean()
        data[f"demand_rolling_std_{window}h"] = rolling.std()

    # Keep the active artifact working until an objectively better candidate is promoted.
    data["Demand_lag_24hr"] = data["demand_lag_24h"]
    data["demand_lag_168hr"] = data["demand_lag_168h"]
    data["demand_rolling_mean_24hr"] = data["demand_rolling_mean_24h"]
    data["demand_rolling_std_24hr"] = data["demand_rolling_std_24h"]
    return data


def required_history_hours(features: Collection[str]) -> int:
    """Return the causal demand history needed by a stored feature schema."""
    needed = 0
    for name in features:
        if name == "Demand_lag_24hr":
            needed = max(needed, 24)
        elif name == "demand_lag_168hr":
            needed = max(needed, 168)
        elif name.startswith("demand_lag_") and name.endswith("h"):
            needed = max(needed, int(name.removeprefix("demand_lag_").removesuffix("h")))
        elif name.startswith("demand_rolling_") and name.endswith("h"):
            needed = max(needed, int(name.rsplit("_", 1)[1].removesuffix("h")))
        elif name in {"demand_rolling_mean_24hr", "demand_rolling_std_24hr"}:
            needed = max(needed, 24)
    return needed
