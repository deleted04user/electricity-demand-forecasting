"""Explicit application configuration; importing this module never reads resources."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Settings:
    root: Path
    data_path: Path
    model_path: Path
    manifest_path: Path
    diagnostics_path: Path
    weather_path: str | None = None
    events_path: str | None = None
    timezone: str = "Africa/Casablanca"
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    sentry_dsn: str | None = field(default=None, repr=False)
    sentry_environment: str = "production"
    max_request_body_bytes: int = 65_536

    @property
    def bundled_data_path(self) -> Path:
        return self.root / "data/electricity_demand_2025.xlsx"

    def __post_init__(self) -> None:
        ZoneInfo(self.timezone)
        if (
            type(self.max_request_body_bytes) is not int
            or not 1_024 <= self.max_request_body_bytes <= 1_048_576
        ):
            raise ValueError("MAX_REQUEST_BODY_BYTES must be an integer between 1024 and 1048576")

    @classmethod
    def from_env(cls, root: Path | None = None) -> Settings:
        base = root if root is not None else Path(__file__).resolve().parents[1]
        return cls(
            root=base,
            data_path=Path(
                os.getenv("ELECTRICITY_DATA_PATH", str(base / "data/electricity_demand_2025.xlsx"))
            ).expanduser(),
            model_path=base / "models/electricity_xgb_prediction_model.pkl",
            manifest_path=base / "models/artifact-manifest.json",
            diagnostics_path=base / "models/diagnostics.json",
            weather_path=os.getenv("WEATHER_FORECAST_PATH"),
            events_path=os.getenv("VERIFIED_EVENTS_PATH"),
            timezone=os.getenv("ELECTRICITY_TIMEZONE", "Africa/Casablanca"),
            cors_origins=tuple(
                origin.strip()
                for origin in os.getenv(
                    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
                ).split(",")
                if origin.strip()
            ),
            sentry_dsn=os.getenv("SENTRY_DSN", "").strip() or None,
            sentry_environment=os.getenv("SENTRY_ENVIRONMENT", "production").strip()
            or "production",
            max_request_body_bytes=int(os.getenv("MAX_REQUEST_BODY_BYTES", "65536")),
        )
