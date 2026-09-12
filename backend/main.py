"""
FastAPI backend for the Electricity Demand Forecasting dashboard.
Serves the same XGBoost model/data as the old Streamlit app, over a JSON API
that a React frontend can consume.
"""
import numpy as np
import pandas as pd
import joblib
from fastapi import FastAPI, HTTPException, Query
from pathlib import Path
import os
from functools import lru_cache
try:
    from .features import add_engineered_features, required_history_hours, _morocco_holiday_dates
    from .modeling import baseline_metrics as calculate_baseline_metrics
    from .modeling import calculate_metrics, rounded_metrics
except ImportError:
    from features import add_engineered_features, required_history_hours, _morocco_holiday_dates
    from modeling import baseline_metrics as calculate_baseline_metrics
    from modeling import calculate_metrics, rounded_metrics
try:
    from .ingestion import configured_data_path, data_quality, load_hourly_data, load_configured_weather, verified_event_dates
except ImportError:
    from ingestion import configured_data_path, data_quality, load_hourly_data, load_configured_weather, verified_event_dates
from fastapi.middleware.cors import CORSMiddleware
from holidays import country_holidays

app = FastAPI(title="Electricity Demand Forecasting API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = ROOT / "data/electricity_demand_2025.xlsx"
DATA_PATH = configured_data_path(DEFAULT_DATA_PATH)
MODEL_PATH = ROOT / "models/electricity_xgb_prediction_model.pkl"


# Load once at startup
raw = load_hourly_data(DATA_PATH)
_years = tuple(range(raw.index.min().year, raw.index.max().year + 1))
EVENT_DATES = verified_event_dates(os.getenv("VERIFIED_EVENTS_PATH"))
DATA = add_engineered_features(raw, holiday_dates=set(_morocco_holiday_dates(_years)).union(EVENT_DATES))
MODEL_PACKAGE = joblib.load(MODEL_PATH)
MODEL = MODEL_PACKAGE["model"]
FEATURES = MODEL_PACKAGE["features"]
FEATURE_IMPORTANCE = MODEL_PACKAGE["feature_importance"]

TEST_START = MODEL_PACKAGE["test_period"]["start"]


@lru_cache(maxsize=1)
def heldout_residual_radius() -> float:
    val = DATA.loc[TEST_START:MODEL_PACKAGE["test_period"]["end"]].dropna(subset=["Demand", *FEATURES])
    return float(np.quantile(np.abs(val["Demand"].to_numpy() - MODEL.predict(val[FEATURES])), .90))


def prediction_interval(prediction: float, horizon: int = 1) -> dict:
    """Empirical absolute-residual interval; an estimate, never a guarantee."""
    # Scaling explicitly acknowledges compounding recursive uncertainty.
    radius = heldout_residual_radius() * np.sqrt(horizon)
    return {"level": 0.90, "lower": round(max(0, prediction - radius), 2), "upper": round(prediction + radius, 2),
            "method": "90% empirical held-out absolute-residual estimate; recursive horizons use sqrt(horizon) scaling", "not_a_guarantee": True}


@app.get("/api/overview")
def overview():
    d = DATA
    return {
        "total_observations": len(d),
        "date_range": {"start": str(d.index.min()), "end": str(d.index.max())},
        "demand_stats": {
            "mean": round(d["Demand"].mean(), 2),
            "std": round(d["Demand"].std(), 2),
            "median": round(d["Demand"].median(), 2),
            "min": round(d["Demand"].min(), 2),
            "max": round(d["Demand"].max(), 2),
            "q1": round(d["Demand"].quantile(0.25), 2),
            "q3": round(d["Demand"].quantile(0.75), 2),
        },
        "temperature_stats": {
            "mean": round(d["Temperature"].mean(), 2),
            "std": round(d["Temperature"].std(), 2),
            "median": round(d["Temperature"].median(), 2),
            "min": round(d["Temperature"].min(), 2),
            "max": round(d["Temperature"].max(), 2),
            "q1": round(d["Temperature"].quantile(0.25), 2),
            "q3": round(d["Temperature"].quantile(0.75), 2),
        },
        # Daily-averaged series so the frontend chart isn't 43k points
        "demand_timeseries": [
            {"date": str(date.date()), "demand": round(val, 2)}
            for date, val in d["Demand"].resample("D").mean().items()
        ],
    }


@app.get("/api/demand-analysis")
def demand_analysis():
    d = DATA
    hourly = d.groupby("hour")["Demand"].mean().round(2)
    monthly = d.groupby("month")["Demand"].mean().round(2)
    weekday_avg = d[d["is_weekend"] == 0]["Demand"].mean()
    weekend_avg = d[d["is_weekend"] == 1]["Demand"].mean()

    corr_cols = ["Demand", "Temperature", "Humidity", "hour", "dayofweek", "month"]
    corr = d[corr_cols].corr().round(2)

    # Downsample scatter data for the frontend (every 6th point ~ every 6 hours)
    # Missing demand targets are intentionally retained in DATA for honest scoring,
    # but JSON responses cannot contain NaN. Filter them before downsampling.
    scatter_sample = d[["Temperature", "Demand"]].dropna().iloc[::6].round(2)

    return {
        "hourly_avg": [{"hour": int(h), "demand": v} for h, v in hourly.items()],
        "monthly_avg": [{"month": int(m), "demand": v} for m, v in monthly.items()],
        "weekday_vs_weekend": {
            "weekday": round(weekday_avg, 2),
            "weekend": round(weekend_avg, 2),
        },
        "temp_vs_demand_sample": [
            {"temperature": row.Temperature, "demand": row.Demand}
            for row in scatter_sample.itertuples()
        ],
        "correlation_matrix": {
            "columns": corr_cols,
            "values": corr.values.tolist(),
        },
    }


@app.get("/api/model-performance")
def model_performance():
    val_data = DATA.loc[TEST_START:MODEL_PACKAGE["test_period"]["end"]].dropna(subset=["Demand"] + FEATURES).copy()
    X_val = val_data[FEATURES].dropna()
    y_val = val_data["Demand"].loc[X_val.index]
    y_pred = MODEL.predict(X_val)

    metrics = rounded_metrics(calculate_metrics(y_val, y_pred))

    errors = (y_val.values - y_pred)

    # Downsample the actual-vs-predicted series for the chart (daily average)
    series_df = pd.DataFrame({"actual": y_val.values, "predicted": y_pred}, index=y_val.index)
    daily = series_df.resample("D").mean().round(2)

    top_features = sorted(FEATURE_IMPORTANCE.items(), key=lambda x: x[1], reverse=True)[:15]

    horizon_metrics = horizon_evaluation()
    return {
        "metrics": metrics,
        "test_period": MODEL_PACKAGE["test_period"],
        "early_stopping_period": MODEL_PACKAGE["early_stopping_period"],
        "baselines": baseline_metrics(val_data),
        "actual_vs_predicted": [
            {"date": str(idx.date()), "actual": row.actual, "predicted": row.predicted}
            for idx, row in daily.iterrows()
        ],
        "error_histogram": np.histogram(errors, bins=40)[0].tolist(),
        "error_bin_edges": np.histogram(errors, bins=40)[1].round(1).tolist(),
        "feature_importance": [{"feature": f, "importance": round(float(v), 4)} for f, v in top_features],
        "horizon_metrics": horizon_metrics,
    }


@app.get("/api/forecast")
def forecast(date: str, hour: int = Query(..., ge=0, le=23)):
    """Look up actual vs predicted demand for a specific historical timestamp
    (demonstration mode -- same behaviour as the old Streamlit 'Forecast' page)."""
    try:
        timestamp = pd.Timestamp(f"{date} {hour:02d}:00:00")
    except ValueError:
        raise HTTPException(400, "Invalid date/hour")

    if timestamp not in DATA.index:
        raise HTTPException(404, f"No data available for {timestamp}")

    row = DATA.loc[[timestamp]]
    if row[FEATURES + ["Demand"]].isna().any().any():
        raise HTTPException(400, "Insufficient observed demand/weather history")
    actual = float(row["Demand"].values[0])
    X_sample = row[FEATURES]
    prediction = float(MODEL.predict(X_sample)[0])

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
        "input_features": {f: float(X_sample[f].values[0]) for f in FEATURES},
        "prediction_interval": prediction_interval(prediction),
    }


@app.get("/api/meta")
def meta():
    return {
        "min_date": str(DATA.index.min().date()),
        "max_date": str(DATA.index.max().date()),
        "future_start": str(DATA.index.max() + pd.Timedelta(hours=1)),
        "data_quality": data_quality(raw, model_features=FEATURES),
        "synthetic_data": DATA_PATH == DEFAULT_DATA_PATH,
        "weather_forecast_configured": bool(os.getenv("WEATHER_FORECAST_PATH")),
        "verified_events_configured": bool(os.getenv("VERIFIED_EVENTS_PATH")),
    }

from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class FutureRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    start: datetime
    horizon: int = Field(default=24, ge=1, le=168, strict=True)
    temperature: list[float] | None = None
    humidity: list[float] | None = None


def metric_values(actual, predicted):
    return rounded_metrics(calculate_metrics(actual, predicted))


def baseline_metrics(frame):
    return {name: rounded_metrics(values) for name, values in calculate_baseline_metrics(frame).items()}


def recursive_forecast(history, start, horizon, temperature=None, humidity=None):
    """Experimental multi-step forecast; errors compound as predictions feed later lags."""
    history = history.loc[history.index < start, ["Demand", "Temperature", "Humidity"]].copy()
    history["Demand"] = history["Demand"].ffill()
    history_hours = required_history_hours(FEATURES)
    required = pd.date_range(end=start - pd.Timedelta(hours=1), periods=history_hours, freq="h")
    if history.reindex(required)["Demand"].isna().any():
        raise HTTPException(400, f"Forecast requires {history_hours} hours of causal demand history before start")
    seasonal = history.groupby([history.index.month, history.index.hour])[["Temperature", "Humidity"]].mean()
    hourly = history.groupby(history.index.hour)[["Temperature", "Humidity"]].mean()
    rows = []
    # Only the recent demand window is needed after fitting historical weather averages.
    history = history.tail(history_hours)
    for i, stamp in enumerate(pd.date_range(start, periods=horizon, freq="h")):
        proxy = seasonal.loc[(stamp.month, stamp.hour)] if (stamp.month, stamp.hour) in seasonal.index else hourly.loc[stamp.hour]
        temp = temperature[i] if temperature is not None else float(proxy.Temperature)
        humid = humidity[i] if humidity is not None else float(proxy.Humidity)
        if not np.isfinite([temp, humid]).all():
            raise HTTPException(400, "Insufficient historical weather for proxy")
        history.loc[stamp] = [np.nan, temp, humid]
        years = tuple(range(history.index.min().year, stamp.year + 1))
        features = add_engineered_features(history, holiday_dates=set(_morocco_holiday_dates(years)).union(EVENT_DATES)).loc[[stamp], FEATURES]
        prediction = float(MODEL.predict(features)[0])
        history.loc[stamp, "Demand"] = prediction
        rows.append({"timestamp": str(stamp), "predicted": round(prediction, 2), "prediction_interval": prediction_interval(prediction, i + 1)})
    return rows


@app.get("/api/health")
def health():
    return {"status": "ok", "model_ready": MODEL is not None,
            "data_ready": not DATA.empty, "observations": len(DATA),
            "data_quality": data_quality(raw, model_features=FEATURES),
            "synthetic_data": DATA_PATH == DEFAULT_DATA_PATH}


@app.post("/api/forecast/future")
def future_forecast(request: FutureRequest):
    start = pd.Timestamp(request.start)
    expected = DATA.index.max() + pd.Timedelta(hours=1)
    if start.tzinfo is not None or start != expected:
        raise HTTPException(400, f"start must be the next historical hour, {expected}, without timezone")
    if (request.temperature is None) != (request.humidity is None):
        raise HTTPException(400, "Supply both temperature and humidity arrays, or omit both")
    for name, values in [("temperature", request.temperature), ("humidity", request.humidity)]:
        if values is not None and len(values) != request.horizon:
            raise HTTPException(400, f"{name} must contain exactly horizon hourly values")
    if request.humidity is not None and any(v < 0 or v > 100 for v in request.humidity):
        raise HTTPException(400, "humidity must be between 0 and 100 percent")
    supplied = request.temperature is not None
    configured_weather = None
    if not supplied:
        try:
            configured_weather = load_configured_weather(os.getenv("WEATHER_FORECAST_PATH"), start, request.horizon)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    if configured_weather is not None:
        request.temperature = configured_weather["Temperature"].tolist()
        request.humidity = configured_weather["Humidity"].tolist()
    return {"forecast_mode": "experimental_recursive",
            "horizon_note": "One-step/short-horizon evaluation does not represent this full recursive horizon; errors can accumulate.",
            "weather_source": "supplied" if supplied else ("configured_local_forecast" if configured_weather is not None else "historical_proxy"),
            "weather_description": "User supplied hourly weather" if supplied else ("Configured local hourly weather forecast" if configured_weather is not None else
            "Deterministic historical month/hour averages (hour averages as fallback); not a real weather forecast"),
            "forecast": recursive_forecast(DATA, start, request.horizon, request.temperature, request.humidity)}


@lru_cache(maxsize=1)
def horizon_evaluation():
    """Fixed 2024 sampled recursive backtest, separate from observed-lag scores."""
    results = {"one_step_observed_lag": None, "recursive_multi_step": {}}
    val = DATA.loc[TEST_START:MODEL_PACKAGE["test_period"]["end"]].dropna(subset=["Demand", *FEATURES])
    results["one_step_observed_lag"] = rounded_metrics(calculate_metrics(val["Demand"], MODEL.predict(val[FEATURES])))
    samples = []
    # Generate each origin once at 168h, then score prefixes for all horizons.
    for start in (pd.Timestamp("2024-02-01"), pd.Timestamp("2024-08-01")):
        rows = recursive_forecast(DATA.loc[DATA.index < start], start, 168)
        target = DATA.reindex(pd.date_range(start, periods=168, freq="h"))["Demand"]
        predictions = [r["predicted"] for r in rows]
        if target.notna().any():
            samples.append((target.tolist(), predictions))
    for horizon in (1, 6, 24, 72, 168):
        actual, predicted = [], []
        for target, forecast in samples:
            for observed, estimate in zip(target[:horizon], forecast[:horizon]):
                if pd.notna(observed):
                    actual.append(observed); predicted.append(estimate)
        results["recursive_multi_step"][str(horizon)] = {"origins": len(samples), "metrics": rounded_metrics(calculate_metrics(actual, predicted)), "weather": "historical_proxy"}
    return results
