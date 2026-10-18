"""A configured service's clock must not change with unrelated process settings."""

import pandas as pd
from backend.ingestion import load_configured_weather, load_hourly_data


def test_explicit_data_timezone_is_independent_of_environment(tmp_path, monkeypatch):
    path = tmp_path / "demand.csv"
    pd.DataFrame(
        {
            "Timestamp": ["2024-01-01T00:00:00Z"],
            "Demand": [100],
            "Temperature": [20],
            "Humidity": [50],
        }
    ).to_csv(path, index=False)
    monkeypatch.setenv("ELECTRICITY_TIMEZONE", "Africa/Casablanca")
    utc = load_hourly_data(path, timezone="UTC")
    local = load_hourly_data(path, timezone="Africa/Casablanca")
    assert utc.index[0] == pd.Timestamp("2024-01-01 00:00:00")
    assert local.index[0] == pd.Timestamp("2024-01-01 01:00:00")
    assert load_hourly_data(path, timezone="UTC").equals(utc)


def test_explicit_weather_timezone_is_independent_of_environment(tmp_path, monkeypatch):
    path = tmp_path / "weather.csv"
    pd.DataFrame(
        {"Timestamp": ["2025-01-01T00:00:00Z"], "Temperature": [20], "Humidity": [50]}
    ).to_csv(path, index=False)
    monkeypatch.setenv("ELECTRICITY_TIMEZONE", "Africa/Casablanca")
    weather = load_configured_weather(str(path), pd.Timestamp("2025-01-01"), 1, timezone="UTC")
    assert weather is not None and weather.iloc[0].Temperature == 20
