"""Finite, documented request and response schemas at the HTTP boundary."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ResponseModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class FutureRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    start: datetime
    horizon: int = Field(default=24, ge=1, le=168, strict=True)
    temperature: list[float] | None = None
    humidity: list[float] | None = None


class UnavailableResponse(ResponseModel):
    detail: str
    status: Literal["unavailable"] = "unavailable"
    error_code: str


class DateRange(ResponseModel):
    start: str
    end: str


class Statistics(ResponseModel):
    mean: float | None
    std: float | None
    median: float | None
    min: float | None
    max: float | None
    q1: float | None
    q3: float | None


class DemandPoint(ResponseModel):
    date: str
    demand: float


class OverviewResponse(ResponseModel):
    total_observations: int
    date_range: DateRange
    demand_stats: Statistics
    temperature_stats: Statistics
    demand_timeseries: list[DemandPoint]


class HourlyDemand(ResponseModel):
    hour: int
    demand: float


class MonthlyDemand(ResponseModel):
    month: int
    demand: float


class Comparison(ResponseModel):
    weekday: float | None
    weekend: float | None


class WeatherDemand(ResponseModel):
    temperature: float
    demand: float


class Correlation(ResponseModel):
    columns: list[str]
    values: list[list[float | None]]


class DemandAnalysisResponse(ResponseModel):
    hourly_avg: list[HourlyDemand]
    monthly_avg: list[MonthlyDemand]
    weekday_vs_weekend: Comparison
    temp_vs_demand_sample: list[WeatherDemand]
    correlation_matrix: Correlation


class Metrics(ResponseModel):
    mae: float | None
    rmse: float | None
    r2: float | None
    wape: float | None
    bias: float | None


class PredictionComparison(ResponseModel):
    date: str
    actual: float
    predicted: float


class FeatureImportance(ResponseModel):
    feature: str
    importance: float


class RecursiveMetrics(ResponseModel):
    origins: int
    scored_rows: int
    metrics: Metrics
    weather: str


class HorizonMetrics(ResponseModel):
    one_step_observed_lag: Metrics
    recursive_multi_step: dict[str, RecursiveMetrics]


class ModelPerformanceResponse(ResponseModel):
    metrics: Metrics
    test_period: DateRange
    early_stopping_period: DateRange
    baselines: dict[str, Metrics]
    actual_vs_predicted: list[PredictionComparison]
    error_histogram: list[int]
    error_bin_edges: list[float]
    feature_importance: list[FeatureImportance]
    horizon_metrics: HorizonMetrics


class PredictionInterval(ResponseModel):
    level: float
    lower: float
    upper: float
    method: str
    not_a_guarantee: bool


class HistoricalContext(ResponseModel):
    temperature: float
    humidity: float
    day_of_week: str
    is_holiday: bool
    is_weekend: bool


class ForecastResponse(ResponseModel):
    timestamp: str
    actual: float
    predicted: float
    error: float
    context: HistoricalContext
    input_features: dict[str, float]
    prediction_interval: PredictionInterval


class FuturePoint(ResponseModel):
    timestamp: str
    predicted: float
    prediction_interval: PredictionInterval


class FutureResponse(ResponseModel):
    forecast_mode: str
    horizon_note: str
    weather_source: str
    weather_description: str
    forecast: list[FuturePoint]


class QualityDateCoverage(ResponseModel):
    start: str | None
    end: str | None


class DataQuality(ResponseModel):
    status: str
    rows: int
    date_coverage: QualityDateCoverage
    duplicates: int
    hourly_gaps: int
    first_gap: str | None
    missing: dict[str, int]
    non_finite: dict[str, int]
    off_hour_timestamps: int
    outliers_iqr_3x: dict[str, int]
    model_data_compatible: bool
    required_history_hours: int
    rules: str


class Provenance(ResponseModel):
    synthetic_data: bool | None
    data_provenance: str


class MetaResponse(Provenance):
    min_date: str
    max_date: str
    future_start: str
    data_quality: DataQuality
    weather_forecast_configured: bool
    verified_events_configured: bool


class HealthResponse(Provenance):
    status: str
    model_ready: bool
    data_ready: bool
    observations: int
    data_quality: DataQuality
