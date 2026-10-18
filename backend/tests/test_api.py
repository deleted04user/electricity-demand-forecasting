import json
import logging
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from backend import main
from backend.features import add_engineered_features
from backend.logging_config import JsonFormatter, logger
from backend.service import ForecastError
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    with TestClient(main.create_app()) as active:
        yield active


@pytest.fixture
def service(client):
    return client.app.state.runtime.service


def test_health_overview_meta(client):
    assert client.get("/api/health").json()["model_ready"]
    assert client.get("/api/overview").json()["total_observations"] > 0
    analysis = client.get("/api/demand-analysis")
    assert analysis.status_code == 200
    assert analysis.json()["temp_vs_demand_sample"]
    meta = client.get("/api/meta").json()
    assert meta["future_start"] == "2025-01-01 00:00:00"
    assert "data_quality" in meta and "model_data_compatible" in meta["data_quality"]


def test_historical(client):
    response = client.get("/api/forecast", params={"date": "2024-12-31", "hour": 12})
    assert response.status_code == 200
    assert response.json()["prediction_interval"]["not_a_guarantee"] is True
    for date, hour, code in [
        ("bad", 12, 400),
        ("2024-01-01", 24, 422),
        ("2030-01-01", 0, 404),
        ("2020-01-01", 0, 400),
    ]:
        assert client.get("/api/forecast", params={"date": date, "hour": hour}).status_code == code


def test_future(client):
    payload = {"start": "2025-01-01T00:00:00", "horizon": 25}
    response = client.post("/api/forecast/future", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["weather_source"] == "historical_proxy"
    assert len(body["forecast"]) == 25
    assert body["forecast"][-1]["timestamp"] == "2025-01-02 00:00:00"
    payload.update(horizon=2, temperature=[20, 21], humidity=[50, 55])
    assert client.post("/api/forecast/future", json=payload).json()["weather_source"] == "supplied"


@pytest.mark.parametrize(
    "change",
    [
        {"horizon": 0},
        {"horizon": 169},
        {"horizon": 1.5},
        {"start": "bad"},
        {"start": "2026-01-01"},
        {"start": "2025-01-01T00:00:00Z"},
        {"temperature": [20]},
        {"temperature": [20], "humidity": [50]},
        {"temperature": [20, 20], "humidity": [101, 50]},
    ],
)
def test_future_validation(client, change):
    response = client.post(
        "/api/forecast/future", json={"start": "2025-01-01", "horizon": 2, **change}
    )
    assert 400 <= response.status_code < 500


def test_causal_features():
    frame = pd.DataFrame(
        {"Demand": np.arange(220, dtype=float), "Temperature": 20.0, "Humidity": 50.0},
        index=pd.date_range("2024-01-01", periods=220, freq="h"),
    )
    frame.loc[frame.index[0], "Temperature"] = np.nan
    frame.loc[frame.index[190], ["Demand", "Temperature"]] = np.nan
    original = add_engineered_features(frame)
    changed = frame.copy()
    changed.loc[frame.index[200] :, :] = 9999
    engineered = add_engineered_features(changed)
    cols = [
        "Demand_lag_24hr",
        "demand_lag_168hr",
        "demand_rolling_mean_24hr",
        "demand_rolling_std_24hr",
    ]
    pd.testing.assert_frame_equal(
        original.loc[: frame.index[200], cols], engineered.loc[: frame.index[200], cols]
    )
    assert original.iloc[200]["Demand_lag_24hr"] == 176
    assert original.iloc[200]["demand_lag_168hr"] == 32
    assert (
        original.iloc[200]["demand_rolling_mean_24hr"] == frame.Demand.ffill().iloc[176:200].mean()
    )
    assert pd.isna(original.iloc[0].Temperature)
    assert original.iloc[190].Temperature == 20
    assert pd.isna(original.iloc[190].Demand)
    assert pd.isna(original.iloc[0]["Demand_lag_24hr"])


def test_recursive_predictions_feed_history(service, monkeypatch):
    class LagModel:
        def predict(self, features):
            column = "demand_lag_24h" if "demand_lag_24h" in features else "Demand_lag_24hr"
            return features[column].to_numpy() + 1

    monkeypatch.setattr(service, "model", LagModel())
    start = pd.Timestamp("2025-01-01")
    rows = service.recursive_forecast(service.data, start, 25)
    assert rows[24]["predicted"] == pytest.approx(rows[0]["predicted"] + 1, abs=0.01)


def test_baselines_and_split(client):
    body = client.get("/api/model-performance").json()
    assert set(body["baselines"]) == {"24-hour naive", "168-hour naive"}
    assert body["early_stopping_period"]["start"].startswith("2023")
    assert body["test_period"]["start"].startswith("2024")
    assert set(body["horizon_metrics"]["recursive_multi_step"]) == {"1", "6", "24", "72", "168"}
    assert body["horizon_metrics"]["one_step_observed_lag"]["wape"] == body["metrics"]["wape"]


@pytest.mark.parametrize(
    "date", ["2024-12-31 12:00", "2024-12-31T00:00:00Z", "20241231", "2024-W52-2"]
)
def test_historical_rejects_dates_with_hidden_time_or_noncanonical_format(client, date):
    response = client.get("/api/forecast", params={"date": date, "hour": 12})
    assert response.status_code == 400


@pytest.mark.parametrize(
    "change",
    [
        {"horizon": True},
        {"unexpected": 1},
        {"temperature": ["NaN", 20], "humidity": [50, 50]},
        {"temperature": [20, 20], "humidity": ["Infinity", 50]},
    ],
)
def test_future_rejects_nonfinite_and_ambiguous_payloads(client, change):
    response = client.post(
        "/api/forecast/future", json={"start": "2025-01-01", "horizon": 2, **change}
    )
    assert response.status_code == 422


def test_future_uses_configured_weather_and_returns_configuration_errors(
    client, service, tmp_path, monkeypatch
):
    path = tmp_path / "weather.csv"
    monkeypatch.setattr(service, "settings", replace(service.settings, weather_path=str(path)))
    payload = {"start": "2025-01-01", "horizon": 2}
    response = client.post("/api/forecast/future", json=payload)
    assert response.status_code == 400
    assert "could not be read" in response.json()["detail"]
    pd.DataFrame(
        {
            "Timestamp": ["2025-01-01", "2025-01-01 01:00"],
            "Temperature": [20, 21],
            "Humidity": [50, 51],
        }
    ).to_csv(path, index=False)
    response = client.post("/api/forecast/future", json=payload)
    assert response.status_code == 200
    assert response.json()["weather_source"] == "configured_local_forecast"


def test_demand_analysis_keeps_json_valid_when_targets_are_missing(client, service, monkeypatch):
    data = service.data.copy()
    data.loc[data.index[100:120], "Demand"] = np.nan
    monkeypatch.setattr(service, "data", data)
    response = client.get("/api/demand-analysis")
    assert response.status_code == 200
    assert all(np.isfinite(row["demand"]) for row in response.json()["temp_vs_demand_sample"])


def test_recursive_forecast_reports_insufficient_history(service):
    with pytest.raises(ForecastError, match="causal demand history"):
        service.recursive_forecast(service.data.iloc[:1], pd.Timestamp("2025-01-01"), 1)


def test_request_logs_and_response_share_request_id_without_query_values(
    client, caplog, monkeypatch
):
    monkeypatch.setattr(logger, "propagate", True)
    with caplog.at_level(logging.INFO, logger="electricity.api"):
        response = client.get("/api/health?token=private-value")
    record = next(record for record in caplog.records if record.getMessage() == "request_completed")
    payload = json.loads(JsonFormatter().format(record))
    assert payload["request_id"] == response.headers["X-Request-ID"]
    assert payload["status_code"] == 200 and payload["duration_ms"] >= 0
    assert payload["method"] == "GET" and payload["path"] == "/api/health"
    assert "private-value" not in json.dumps(payload)


def test_unexpected_failure_is_logged_and_returns_safe_json(client, service, monkeypatch, caplog):
    class BrokenModel:
        def predict(self, features):
            raise RuntimeError("private implementation detail")

    monkeypatch.setattr(service, "model", BrokenModel())
    monkeypatch.setattr(logger, "propagate", True)
    with caplog.at_level(logging.INFO, logger="electricity.api"):
        response = client.get("/api/forecast", params={"date": "2024-12-31", "hour": 12})
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    error = next(record for record in caplog.records if record.getMessage() == "request_failed")
    assert error.request_id == response.headers["X-Request-ID"]
    assert error.error_type == "RuntimeError"
