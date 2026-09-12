"""Local data contract and quality checks for hourly demand/weather inputs.

No network access is performed here.  Set ``ELECTRICITY_DATA_PATH`` to a CSV or
XLSX file to use a local operational feed; otherwise the bundled demonstration
file is used.  The canonical columns are Timestamp, Demand, Temperature and
Humidity.  Timestamp must be an unambiguous hourly local time (configured by
``ELECTRICITY_TIMEZONE``; default Africa/Casablanca).  Inputs may be naive local
timestamps or timezone-aware timestamps, but not a mixture.
"""
from __future__ import annotations

import os
from pathlib import Path
import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("Timestamp", "Demand", "Temperature", "Humidity")


def configured_data_path(default: Path) -> Path:
    return Path(os.getenv("ELECTRICITY_DATA_PATH", str(default))).expanduser()


def _read(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError("Data input must be a .csv, .xlsx, or .xls file")


def load_hourly_data(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Configured data file does not exist: {path}")
    raw = _read(path).dropna(how="all")
    missing = sorted(set(REQUIRED_COLUMNS).difference(raw.columns))
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    data = raw.loc[:, list(REQUIRED_COLUMNS)].copy()
    data["Timestamp"] = pd.to_datetime(data["Timestamp"], errors="coerce")
    if data["Timestamp"].isna().any():
        raise ValueError("Timestamp contains invalid values")
    # Convert aware source timestamps to configured local clock time, then retain
    # naive local timestamps for the model's established artifact contract.
    if getattr(data["Timestamp"].dt, "tz", None) is not None:
        data["Timestamp"] = data["Timestamp"].dt.tz_convert(os.getenv("ELECTRICITY_TIMEZONE", "Africa/Casablanca")).dt.tz_localize(None)
    for column in ("Demand", "Temperature", "Humidity"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return data.set_index("Timestamp").sort_index()


def data_quality(frame: pd.DataFrame, *, model_features=()) -> dict:
    """Return transparent, non-mutating data checks; no values are imputed."""
    index = frame.index
    duplicates = int(index.duplicated().sum())
    unique = index[~index.duplicated()]
    expected = pd.date_range(unique.min(), unique.max(), freq="h") if len(unique) else pd.DatetimeIndex([])
    gaps = expected.difference(unique)
    numeric = frame[[c for c in ("Demand", "Temperature", "Humidity") if c in frame]].copy()
    outliers = {}
    for column in numeric:
        values = numeric[column].dropna()
        if values.empty:
            outliers[column] = 0
            continue
        q1, q3 = values.quantile([.25, .75])
        iqr = q3 - q1
        outliers[column] = int(((values < q1 - 3 * iqr) | (values > q3 + 3 * iqr)).sum()) if iqr else 0
    missing = {column.lower(): int(frame[column].isna().sum()) for column in numeric}
    required_history = 0
    from .features import required_history_hours
    required_history = required_history_hours(model_features) if model_features else 0
    compatible = (duplicates == 0 and len(gaps) == 0 and all(v == 0 for v in missing.values())
                  and len(frame) > required_history)
    return {
        "status": "ready" if compatible else "attention_required",
        "rows": int(len(frame)),
        "date_coverage": {"start": str(unique.min()) if len(unique) else None, "end": str(unique.max()) if len(unique) else None},
        "duplicates": duplicates, "hourly_gaps": int(len(gaps)),
        "first_gap": str(gaps[0]) if len(gaps) else None,
        "missing": missing, "outliers_iqr_3x": outliers,
        "model_data_compatible": compatible,
        "required_history_hours": required_history,
        "rules": "No duplicate timestamps or gaps; demand/weather must be present for model-compatible rows. Outliers are flagged, not removed.",
    }


def load_configured_weather(path_value: str | None, start: pd.Timestamp, horizon: int):
    """Read a credential-free locally supplied weather forecast file if configured."""
    if not path_value:
        return None
    path = Path(path_value)
    weather = _read(path)
    missing = sorted({"Timestamp", "Temperature", "Humidity"}.difference(weather.columns))
    if missing:
        raise ValueError(f"Weather forecast is missing required columns: {', '.join(missing)}")
    weather = weather[["Timestamp", "Temperature", "Humidity"]].copy()
    weather["Timestamp"] = pd.to_datetime(weather["Timestamp"], errors="coerce")
    weather["Temperature"] = pd.to_numeric(weather["Temperature"], errors="coerce")
    weather["Humidity"] = pd.to_numeric(weather["Humidity"], errors="coerce")
    weather = weather.set_index("Timestamp").sort_index()
    future = weather.reindex(pd.date_range(start, periods=horizon, freq="h"))
    if future[["Temperature", "Humidity"]].isna().any().any():
        raise ValueError("Configured weather forecast does not cover every requested hour")
    return future


def verified_event_dates(path_value: str | None) -> set:
    """Load explicitly maintained event dates; missing configuration means no added events."""
    if not path_value:
        return set()
    events = _read(Path(path_value))
    if "Date" not in events.columns or "Event" not in events.columns:
        raise ValueError("Verified event file requires Date and Event columns")
    dates = pd.to_datetime(events["Date"], errors="coerce")
    if dates.isna().any() or events["Event"].isna().any():
        raise ValueError("Verified event file contains invalid Date or Event values")
    return set(dates.dt.date)
