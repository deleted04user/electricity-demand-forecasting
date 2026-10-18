"""Shared forecasting runtime; HTTP and evaluation callers own explicit instances."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import date as calendar_date
from functools import cached_property
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from .api_models import FutureRequest, ModelPerformanceResponse
from .artifacts import ArtifactError, file_sha256, load_model, source_sha256
from .diagnostics import descriptive_statistics, horizons, nullable_number, performance
from .features import _morocco_holiday_dates, add_engineered_features, required_history_hours
from .ingestion import (
    data_provenance,
    data_quality,
    load_configured_weather,
    load_hourly_data,
    verified_event_dates,
)
from .settings import Settings


class ForecastError(ValueError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class ForecastService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        artifact = load_model(settings.model_path, settings.manifest_path)
        self.model = artifact.model
        self.package = artifact.package
        self.features = artifact.features
        self.model_sha256 = artifact.sha256
        self.data_sha256 = file_sha256(settings.data_path)
        self.raw = load_hourly_data(settings.data_path, timezone=settings.timezone)
        if file_sha256(settings.data_path) != self.data_sha256:
            raise ArtifactError("Data changed during initialization; reload a stable input")
        self.provenance = data_provenance(settings.data_path, settings.bundled_data_path)
        self.events = verified_event_dates(settings.events_path)
        years = tuple(range(self.raw.index.min().year, self.raw.index.max().year + 1))
        self.data = add_engineered_features(
            self.raw, holiday_dates=set(_morocco_holiday_dates(years)).union(self.events)
        )
        if any(feature not in self.data for feature in self.features):
            raise ArtifactError("Data cannot produce the model feature schema")
        self.test_start = self.package["test_period"]["start"]
        test = self.data.loc[self.test_start : self.package["test_period"]["end"]].dropna(
            subset=["Demand", *self.features]
        )
        if len(test) < 2:
            raise ArtifactError("At least two usable held-out rows are required")
        if not np.isfinite(test[self.features].to_numpy()).all():
            raise ArtifactError("Model inputs must contain finite values")
        probe = np.asarray(self.model.predict(test[self.features]))
        if probe.shape != (len(test),) or not np.isfinite(probe).all():
            raise ArtifactError("Model predictions must be finite and match the input rows")
        self.identity = self._identity()
        self._horizon_cache: dict[str, Any] | None = None
        self._performance_cache: dict[str, Any] | None = None
        self.closed = False

    @classmethod
    def load(cls, settings: Settings) -> ForecastService:
        service = cls(settings)
        try:
            service.warm_diagnostics()
        except Exception:
            service.close()
            raise
        return service

    def _identity(self) -> str:
        payload = {
            "model": self.model_sha256,
            "data": self.data_sha256,
            "events": sorted(str(value) for value in self.events),
            "features": self.features,
            "timezone": self.settings.timezone,
            "runtime_versions": {
                name: version(name) for name in ("numpy", "pandas", "xgboost", "holidays")
            },
            "diagnostic_code": {
                name: source_sha256(Path(__file__).with_name(name))
                for name in (
                    "features.py",
                    "ingestion.py",
                    "modeling.py",
                    "service.py",
                    "diagnostics.py",
                )
            },
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def warm_diagnostics(self) -> None:
        """Warm at lifecycle startup; ordinary requests only read prepared results."""
        try:
            snapshot = json.loads(self.settings.diagnostics_path.read_text(encoding="utf-8"))
            if snapshot["identity"] == self.identity:
                # Schema validation also rejects NaN/Infinity in cached responses.
                self._performance_cache = ModelPerformanceResponse.model_validate(
                    snapshot["performance"]
                ).model_dump()
                self._horizon_cache = self._performance_cache["horizon_metrics"]
                return
        except (OSError, ValueError, KeyError, TypeError):
            pass
        self._horizon_cache = self._compute_horizon_evaluation()
        self._performance_cache = self._compute_model_performance()
        ModelPerformanceResponse.model_validate(self._performance_cache)

    def write_diagnostics(self) -> None:
        temporary = self.settings.diagnostics_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(
                {
                    "identity": self.identity,
                    "performance": ModelPerformanceResponse.model_validate(
                        self.model_performance()
                    ).model_dump(),
                },
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.settings.diagnostics_path)

    def close(self) -> None:
        self._horizon_cache = None
        self._performance_cache = None
        self.__dict__.pop("heldout_residual_radius", None)
        self.closed = True

    def model_performance(self) -> dict[str, Any]:
        if self.closed or self._performance_cache is None:
            raise RuntimeError("Forecast service diagnostics have not been initialized")
        return self._performance_cache

    def horizon_evaluation(self) -> dict[str, Any]:
        if self.closed or self._horizon_cache is None:
            raise RuntimeError("Forecast service diagnostics have not been initialized")
        return self._horizon_cache

    @cached_property
    def heldout_residual_radius(self) -> float:
        val = self.data.loc[self.test_start : self.package["test_period"]["end"]].dropna(
            subset=["Demand", *self.features]
        )
        return float(
            np.quantile(
                np.abs(val["Demand"].to_numpy() - self.model.predict(val[self.features])), 0.90
            )
        )

    def prediction_interval(self, prediction: float, horizon: int = 1) -> dict[str, Any]:
        """Empirical absolute-residual interval; an estimate, never a guarantee."""
        # Scaling explicitly acknowledges compounding recursive uncertainty.
        radius = self.heldout_residual_radius * np.sqrt(horizon)
        return {
            "level": 0.90,
            "lower": round(max(0, prediction - radius), 2),
            "upper": round(prediction + radius, 2),
            "method": "90% empirical held-out absolute-residual estimate; recursive horizons use sqrt(horizon) scaling",
            "not_a_guarantee": True,
        }

    def overview(self) -> dict[str, Any]:
        d = self.data
        return {
            "total_observations": len(d),
            "date_range": {"start": str(d.index.min()), "end": str(d.index.max())},
            "demand_stats": descriptive_statistics(d["Demand"]),
            "temperature_stats": descriptive_statistics(d["Temperature"]),
            # Daily-averaged series so the frontend chart isn't 43k points
            "demand_timeseries": [
                {"date": str(cast(pd.Timestamp, date).date()), "demand": round(val, 2)}
                for date, val in d["Demand"].resample("D").mean().dropna().items()
            ],
        }

    def demand_analysis(self) -> dict[str, Any]:
        d = self.data
        hourly = d.groupby("hour")["Demand"].mean().dropna().round(2)
        monthly = d.groupby("month")["Demand"].mean().dropna().round(2)
        weekday_avg = d[d["is_weekend"] == 0]["Demand"].mean()
        weekend_avg = d[d["is_weekend"] == 1]["Demand"].mean()

        corr_cols = ["Demand", "Temperature", "Humidity", "hour", "dayofweek", "month"]
        corr = d[corr_cols].corr().round(2)

        # Downsample scatter data for the frontend (every 6th point ~ every 6 hours)
        # Missing demand targets are intentionally retained in self.data for honest scoring,
        # but JSON responses cannot contain NaN. Filter them before downsampling.
        scatter_sample = d[["Temperature", "Demand"]].dropna().iloc[::6].round(2)

        return {
            "hourly_avg": [{"hour": int(cast(int, h)), "demand": v} for h, v in hourly.items()],
            "monthly_avg": [{"month": int(cast(int, m)), "demand": v} for m, v in monthly.items()],
            "weekday_vs_weekend": {
                "weekday": nullable_number(round(weekday_avg, 2)),
                "weekend": nullable_number(round(weekend_avg, 2)),
            },
            "temp_vs_demand_sample": [
                {"temperature": row.Temperature, "demand": row.Demand}
                for row in scatter_sample.itertuples()
            ],
            "correlation_matrix": {
                "columns": corr_cols,
                "values": [[nullable_number(value) for value in row] for row in corr.to_numpy()],
            },
        }

    def _compute_model_performance(self) -> dict[str, Any]:
        return performance(self)

    def _predict_one(self, features: pd.DataFrame) -> float:
        values = features.to_numpy(dtype=float)
        if not np.isfinite(values).all() or (np.abs(values) > np.finfo(np.float32).max).any():
            raise ForecastError(
                400, "Forecast features must be finite and representable as float32"
            )
        predictions = np.asarray(self.model.predict(features))
        if predictions.shape != (1,) or not np.isfinite(predictions).all():
            raise ForecastError(503, "nonfinite_model_prediction")
        return float(predictions[0])

    def forecast(self, date: str, hour: int) -> dict[str, Any]:
        """Look up actual vs predicted demand for a specific historical timestamp
        (demonstration mode -- same behaviour as the old Streamlit 'Forecast' page)."""
        try:
            # A date must not smuggle a second time or timezone past the separate hour.
            parsed_date = calendar_date.fromisoformat(date)
            if parsed_date.isoformat() != date:
                raise ValueError("Date must use YYYY-MM-DD")
            timestamp = pd.Timestamp(parsed_date) + pd.Timedelta(hours=hour)
        except (ValueError, OverflowError):
            raise ForecastError(400, "date must use YYYY-MM-DD") from None

        if timestamp not in self.data.index:
            raise ForecastError(404, f"No data available for {timestamp}")

        row = self.data.loc[[timestamp]]
        if row[self.features + ["Demand"]].isna().any().any():
            raise ForecastError(400, "Insufficient observed demand/weather history")
        actual = float(row["Demand"].values[0])
        X_sample = row[self.features]
        prediction = self._predict_one(X_sample)

        return {
            "timestamp": str(timestamp),
            "actual": round(actual, 2),
            "predicted": round(prediction, 2),
            "error": round(abs(actual - prediction), 2),
            "context": {
                "temperature": round(float(row["Temperature"].values[0]), 1),
                "humidity": round(float(row["Humidity"].values[0]), 1),
                "day_of_week": timestamp.day_name(),
                "is_holiday": bool(row["is_holiday"].values[0]),
                "is_weekend": bool(row["is_weekend"].values[0]),
            },
            "input_features": {f: float(X_sample[f].values[0]) for f in self.features},
            "prediction_interval": self.prediction_interval(prediction),
        }

    def meta(self) -> dict[str, Any]:
        return {
            "min_date": str(self.data.index.min().date()),
            "max_date": str(self.data.index.max().date()),
            "future_start": str(self.data.index.max() + pd.Timedelta(hours=1)),
            "data_quality": data_quality(self.raw, model_features=self.features),
            **self.provenance,
            "weather_forecast_configured": bool(self.settings.weather_path),
            "verified_events_configured": bool(self.settings.events_path),
        }

    def recursive_forecast(
        self,
        history: pd.DataFrame,
        start: pd.Timestamp,
        horizon: int,
        temperature: Sequence[float] | None = None,
        humidity: Sequence[float] | None = None,
    ) -> list[dict[str, Any]]:
        """Experimental multi-step forecast; errors compound as predictions feed later lags."""
        history = history.loc[history.index < start, ["Demand", "Temperature", "Humidity"]].copy()
        history["Demand"] = history["Demand"].ffill()
        history_hours = required_history_hours(self.features)
        required = pd.date_range(end=start - pd.Timedelta(hours=1), periods=history_hours, freq="h")
        if history.reindex(required)["Demand"].isna().any():
            raise ForecastError(
                400,
                f"Forecast requires {history_hours} hours of causal demand history before start",
            )
        history_index = pd.DatetimeIndex(history.index)
        seasonal = history.groupby([history_index.month, history_index.hour])[
            ["Temperature", "Humidity"]
        ].mean()
        hourly = history.groupby(history_index.hour)[["Temperature", "Humidity"]].mean()
        rows = []
        # Only the recent demand window is needed after fitting historical weather averages.
        history = history.tail(history_hours)
        for i, stamp in enumerate(pd.date_range(start, periods=horizon, freq="h")):
            proxy = cast(
                "pd.Series[Any]",
                (
                    seasonal.loc[(stamp.month, stamp.hour)]
                    if (stamp.month, stamp.hour) in seasonal.index
                    else hourly.loc[stamp.hour]
                ),
            )
            temp = temperature[i] if temperature is not None else float(proxy["Temperature"])
            humid = humidity[i] if humidity is not None else float(proxy["Humidity"])
            if not np.isfinite([temp, humid]).all():
                raise ForecastError(400, "Insufficient historical weather for proxy")
            history.loc[stamp] = [np.nan, temp, humid]
            years = tuple(range(history.index.min().year, stamp.year + 1))
            with np.errstate(over="ignore", invalid="ignore"):
                engineered = add_engineered_features(
                    history, holiday_dates=set(_morocco_holiday_dates(years)).union(self.events)
                )
            features = engineered[self.features].loc[[stamp]]
            prediction = self._predict_one(features)
            history.loc[stamp, "Demand"] = prediction
            rows.append(
                {
                    "timestamp": str(stamp),
                    "predicted": round(prediction, 2),
                    "prediction_interval": self.prediction_interval(prediction, i + 1),
                }
            )
        return rows

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "model_ready": not self.closed,
            "data_ready": not self.data.empty,
            "observations": len(self.data),
            "data_quality": data_quality(self.raw, model_features=self.features),
            **self.provenance,
        }

    def future_forecast(self, request: FutureRequest) -> dict[str, Any]:
        start = pd.Timestamp(request.start)
        expected = self.data.index.max() + pd.Timedelta(hours=1)
        if start.tzinfo is not None or start != expected:
            raise ForecastError(
                400, f"start must be the next historical hour, {expected}, without timezone"
            )
        if (request.temperature is None) != (request.humidity is None):
            raise ForecastError(400, "Supply both temperature and humidity arrays, or omit both")
        for name, values in [("temperature", request.temperature), ("humidity", request.humidity)]:
            if values is not None and len(values) != request.horizon:
                raise ForecastError(400, f"{name} must contain exactly horizon hourly values")
        if request.humidity is not None and any(v < 0 or v > 100 for v in request.humidity):
            raise ForecastError(400, "humidity must be between 0 and 100 percent")
        supplied = request.temperature is not None
        configured_weather = None
        if not supplied:
            try:
                configured_weather = load_configured_weather(
                    self.settings.weather_path,
                    start,
                    request.horizon,
                    timezone=self.settings.timezone,
                )
            except ValueError as exc:
                raise ForecastError(400, str(exc))
        if configured_weather is not None:
            request.temperature = configured_weather["Temperature"].tolist()
            request.humidity = configured_weather["Humidity"].tolist()
        return {
            "forecast_mode": "experimental_recursive",
            "horizon_note": "One-step/short-horizon evaluation does not represent this full recursive horizon; errors can accumulate.",
            "weather_source": "supplied"
            if supplied
            else (
                "configured_local_forecast"
                if configured_weather is not None
                else "historical_proxy"
            ),
            "weather_description": "User supplied hourly weather"
            if supplied
            else (
                "Configured local hourly weather forecast"
                if configured_weather is not None
                else "Deterministic historical month/hour averages (hour averages as fallback); not a real weather forecast"
            ),
            "forecast": self.recursive_forecast(
                self.data, start, request.horizon, request.temperature, request.humidity
            ),
        }

    def _compute_horizon_evaluation(self) -> dict[str, Any]:
        return horizons(self)
