import pandas as pd
import pytest

from backend.ingestion import data_quality, load_hourly_data, load_configured_weather, verified_event_dates


def test_data_quality_reports_gaps_duplicates_and_missing():
    index = pd.to_datetime(["2024-01-01 00:00", "2024-01-01 00:00", "2024-01-01 02:00"])
    frame = pd.DataFrame({"Demand": [1, None, 3], "Temperature": [20, 20, 20], "Humidity": [50, 50, None]}, index=index)
    status = data_quality(frame, model_features=("demand_lag_24h",))
    assert status["duplicates"] == 1 and status["hourly_gaps"] == 1
    assert status["missing"]["demand"] == 1 and not status["model_data_compatible"]


def test_local_weather_and_verified_events_contract(tmp_path):
    weather = tmp_path / "weather.csv"
    pd.DataFrame({"Timestamp": ["2025-01-01 00:00", "2025-01-01 01:00"], "Temperature": [20, 21], "Humidity": [50, 51]}).to_csv(weather, index=False)
    loaded = load_configured_weather(str(weather), pd.Timestamp("2025-01-01"), 2)
    assert loaded.Temperature.tolist() == [20, 21]
    events = tmp_path / "events.csv"
    pd.DataFrame({"Date": ["2025-01-01"], "Event": ["Verified maintenance"]}).to_csv(events, index=False)
    assert pd.Timestamp("2025-01-01").date() in verified_event_dates(str(events))
    with pytest.raises(ValueError):
        load_configured_weather(str(weather), pd.Timestamp("2025-01-01"), 3)
