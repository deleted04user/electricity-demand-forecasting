import numpy as np
import pandas as pd
import pytest
from backend.ingestion import (
    data_provenance,
    data_quality,
    load_configured_weather,
    load_hourly_data,
    verified_event_dates,
)


def test_provenance_identifies_bundled_content_and_preserves_unknown_sources(tmp_path):
    bundled = tmp_path / "bundled.xlsx"
    bundled.write_bytes(b"known synthetic workbook")
    copy = tmp_path / "renamed.xlsx"
    copy.write_bytes(bundled.read_bytes())
    external = tmp_path / "external.csv"
    external.write_bytes(b"caller supplied measurements")
    for path in (bundled, copy):
        assert data_provenance(path, bundled) == {
            "synthetic_data": True,
            "data_provenance": "bundled_synthetic",
        }
    assert data_provenance(external, bundled) == {
        "synthetic_data": None,
        "data_provenance": "caller_supplied_unverified",
    }


def test_data_quality_reports_gaps_duplicates_and_missing():
    index = pd.to_datetime(["2024-01-01 00:00", "2024-01-01 00:00", "2024-01-01 02:00"])
    frame = pd.DataFrame(
        {"Demand": [1, None, 3], "Temperature": [20, 20, 20], "Humidity": [50, 50, None]},
        index=index,
    )
    status = data_quality(frame, model_features=("demand_lag_24h",))
    assert status["duplicates"] == 1 and status["hourly_gaps"] == 1
    assert status["missing"]["demand"] == 1 and not status["model_data_compatible"]


def test_local_weather_and_verified_events_contract(tmp_path):
    weather = tmp_path / "weather.csv"
    pd.DataFrame(
        {
            "Timestamp": ["2025-01-01 00:00", "2025-01-01 01:00"],
            "Temperature": [20, 21],
            "Humidity": [50, 51],
        }
    ).to_csv(weather, index=False)
    loaded = load_configured_weather(str(weather), pd.Timestamp("2025-01-01"), 2)
    assert loaded.Temperature.tolist() == [20, 21]
    events = tmp_path / "events.csv"
    pd.DataFrame({"Date": ["2025-01-01"], "Event": ["Verified maintenance"]}).to_csv(
        events, index=False
    )
    assert pd.Timestamp("2025-01-01").date() in verified_event_dates(str(events))
    with pytest.raises(ValueError):
        load_configured_weather(str(weather), pd.Timestamp("2025-01-01"), 3)


def hourly_frame():
    return pd.DataFrame(
        {
            "Timestamp": ["2024-01-01 00:00", "2024-01-01 02:00"],
            "Demand": [100, None],
            "Temperature": [20, 21],
            "Humidity": [50, 51],
        }
    )


def test_hourly_loader_preserves_missing_observations_and_sorts(tmp_path):
    path = tmp_path / "demand.csv"
    hourly_frame().iloc[::-1].to_csv(path, index=False)
    loaded = load_hourly_data(path)
    assert loaded.index.is_monotonic_increasing
    assert pd.isna(loaded.iloc[1].Demand)
    status = data_quality(loaded)
    assert status["hourly_gaps"] == 1 and status["missing"]["demand"] == 1
    assert status["status"] == "attention_required"


@pytest.mark.parametrize(
    ("column", "values", "message"),
    [
        ("Timestamp", ["bad", "2024-01-01 02:00"], "invalid"),
        ("Timestamp", ["2024-01-01 00:30", "2024-01-01 02:00"], "hourly boundaries"),
        ("Timestamp", ["2024-01-01 00:00", "2024-01-01 00:00"], "Duplicate"),
        ("Timestamp", ["2024-01-01 00:00Z", "2024-01-01 02:00"], "mix"),
        ("Demand", [100, -1], "non-negative"),
        ("Demand", [100, "unknown"], "non-numeric"),
        ("Temperature", [20, np.inf], "finite"),
        ("Humidity", [50, 101], "between 0 and 100"),
    ],
)
def test_hourly_loader_rejects_invalid_inputs(tmp_path, column, values, message):
    frame = hourly_frame()
    frame[column] = values
    path = tmp_path / "invalid.csv"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match=message):
        load_hourly_data(path)


def test_hourly_loader_normalizes_timezone_and_detects_local_duplicates(tmp_path, monkeypatch):
    monkeypatch.setenv("ELECTRICITY_TIMEZONE", "Africa/Casablanca")
    frame = hourly_frame()
    frame["Timestamp"] = ["2024-01-01T00:00:00Z", "2024-01-01T02:00:00Z"]
    path = tmp_path / "aware.csv"
    frame.to_csv(path, index=False)
    assert load_hourly_data(path).index[0] == pd.Timestamp("2024-01-01 01:00")
    # Casablanca repeated 02:00 when the UTC offset changed for Ramadan.
    frame["Timestamp"] = ["2024-03-10T01:00:00Z", "2024-03-10T02:00:00Z"]
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match="Duplicate"):
        load_hourly_data(path)


def test_empty_or_missing_data_contract(tmp_path):
    path = tmp_path / "data.csv"
    with pytest.raises(FileNotFoundError):
        load_hourly_data(path)
    hourly_frame().iloc[:0].to_csv(path, index=False)
    with pytest.raises(ValueError, match="at least one"):
        load_hourly_data(path)
    hourly_frame().drop(columns="Demand").to_csv(path, index=False)
    with pytest.raises(ValueError, match="Missing required columns: Demand"):
        load_hourly_data(path)
    unsupported = tmp_path / "data.json"
    unsupported.write_text("{}")
    with pytest.raises(ValueError, match="must be a"):
        load_hourly_data(unsupported)


@pytest.mark.parametrize(
    ("column", "values", "message"),
    [
        ("Timestamp", ["2025-01-01 00:00", "2025-01-01 00:00"], "Duplicate"),
        ("Timestamp", ["bad", "2025-01-01 01:00"], "invalid"),
        ("Timestamp", ["2025-01-01 00:30", "2025-01-01 01:00"], "hourly boundaries"),
        ("Temperature", [20, -np.inf], "finite"),
        ("Humidity", [50, -1], "between 0 and 100"),
    ],
)
def test_weather_loader_rejects_invalid_inputs(tmp_path, column, values, message):
    frame = pd.DataFrame(
        {
            "Timestamp": ["2025-01-01 00:00", "2025-01-01 01:00"],
            "Temperature": [20, 21],
            "Humidity": [50, 51],
        }
    )
    frame[column] = values
    path = tmp_path / "weather.csv"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match=message):
        load_configured_weather(str(path), pd.Timestamp("2025-01-01"), 2)


def test_weather_configuration_and_timezone_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("ELECTRICITY_TIMEZONE", "Africa/Casablanca")
    start = pd.Timestamp("2025-01-01 01:00")
    assert load_configured_weather(None, start, 1) is None
    path = tmp_path / "weather.csv"
    with pytest.raises(ValueError, match="could not be read"):
        load_configured_weather(str(path), start, 1)
    pd.DataFrame(
        {"Timestamp": ["2025-01-01T00:00:00Z"], "Temperature": [20], "Humidity": [50]}
    ).to_csv(path, index=False)
    assert load_configured_weather(str(path), start, 1).index[0] == start
    pd.DataFrame({"Timestamp": ["2025-01-01 01:00"]}).to_csv(path, index=False)
    with pytest.raises(ValueError, match="missing required columns"):
        load_configured_weather(str(path), start, 1)


def test_quality_never_marks_infinite_or_partial_columns_ready():
    frame = (
        hourly_frame()
        .set_index(pd.date_range("2024-01-01", periods=2, freq="h"))
        .drop(columns="Timestamp")
    )
    frame["Demand"] = [100, np.inf]
    assert not data_quality(frame)["model_data_compatible"]
    frame["Demand"] = 100
    assert data_quality(frame)["model_data_compatible"]
    assert not data_quality(frame.drop(columns="Humidity"))["model_data_compatible"]


def test_verified_events_reject_missing_schema_and_invalid_values(tmp_path):
    assert verified_event_dates(None) == set()
    path = tmp_path / "events.csv"
    pd.DataFrame({"Date": ["2025-01-01"]}).to_csv(path, index=False)
    with pytest.raises(ValueError, match="requires Date and Event"):
        verified_event_dates(str(path))
    pd.DataFrame({"Date": ["not-a-date"], "Event": ["Maintenance"]}).to_csv(path, index=False)
    with pytest.raises(ValueError, match="invalid Date or Event"):
        verified_event_dates(str(path))
