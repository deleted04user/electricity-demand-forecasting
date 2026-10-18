"""Offline, predeclared research protocol; no serving or promotion imports."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .features import IMPROVED_FEATURES, add_engineered_features
from .modeling import ROLLING_FOLDS, calculate_metrics

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs/experiments.json"
DATA_PATH = ROOT / "data/electricity_demand_2025.xlsx"
VARIANTS = ("lags", "lags_weather", "lags_calendar", "lags_rolling", "full")
LAGS = tuple(name for name in IMPROVED_FEATURES if name.startswith("demand_lag_"))
ROLLING = tuple(name for name in IMPROVED_FEATURES if name.startswith("demand_rolling_"))
WEATHER = ("Temperature", "Humidity", "temperature_squared")
CALENDAR = tuple(name for name in IMPROVED_FEATURES if name not in (*LAGS, *ROLLING, *WEATHER))
FEATURE_GROUPS = {
    "lags": LAGS,
    "lags_weather": (*LAGS, *WEATHER),
    "lags_calendar": (*LAGS, *CALENDAR),
    "lags_rolling": (*LAGS, *ROLLING),
    "full": tuple(IMPROVED_FEATURES),
}


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Reject altered data, folds, selection rules and budgets before any fit.

    The checked-in protocol is the reference, not arbitrary executable config.
    CPU/tree/time budgets may be lowered within the hard limits; changing the
    scientific design requires a versioned code/config change and new review.
    """
    config = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "protocol_version": 1,
        "dataset": "bundled_synthetic",
        "purpose": "research_only_no_promotion",
        "folds": [fold.name for fold in ROLLING_FOLDS],
        "variants": list(VARIANTS),
        "initial_seed": 42,
        "repeat_variants": ["lags", "full"],
        "repeat_seeds": [43, 44],
        "metrics": ["mae", "rmse", "r2", "wape", "bias"],
        "selection": "seed42_mean_fold_wape_then_rmse",
        "weather": "previous_observed_hour",
    }
    if not isinstance(config, dict) or set(config) != {
        *expected,
        "parameters",
        "budget",
        "historical_diagnostics",
    }:
        raise ValueError("Unknown or missing experiment protocol fields")
    for name, value in expected.items():
        if config[name] != value:
            raise ValueError(f"Unsupported predeclared protocol field: {name}")
    params = config["parameters"]
    expected_params = {
        "learning_rate": 0.06,
        "max_depth": 4,
        "min_child_weight": 5,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "reg_alpha": 0.1,
        "reg_lambda": 3.0,
    }
    if not isinstance(params, dict) or set(params) != {*expected_params, "n_estimators"}:
        raise ValueError("Unknown or missing model parameters")
    for name, value in expected_params.items():
        if params[name] != value:
            raise ValueError(f"Unsupported model parameter: {name}")
    trees = params["n_estimators"]
    budget = config["budget"]
    if not isinstance(budget, dict) or set(budget) != {"max_fits", "max_seconds", "threads"}:
        raise ValueError("Unknown or missing budget fields")
    for name, value, minimum, maximum in (
        ("n_estimators", trees, 1, 120),
        ("max_fits", budget["max_fits"], planned_fits(config), 28),
        ("max_seconds", budget["max_seconds"], 1, 300),
        ("threads", budget["threads"], 1, 2),
    ):
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError(
                f"Budget violation: {name} must be an integer in [{minimum}, {maximum}]"
            )
    diagnostics = {
        "start": "2024-01-01",
        "end": "2024-12-31 23:00:00",
        "origin_days": [1],
        "horizons": [1, 6, 24, 72, 168],
        "nominal_coverage": 0.9,
        "interval_rule": "2023_oof_absolute_residual_q90_times_sqrt_horizon",
    }
    if config["historical_diagnostics"] != diagnostics:
        raise ValueError("Unsupported historical diagnostic protocol")
    return config


def planned_fits(config: dict[str, Any]) -> int:
    return (
        len(config["folds"])
        * (len(config["variants"]) + len(config["repeat_variants"]) * len(config["repeat_seeds"]))
        + 1
    )


@dataclass
class Budget:
    """Cooperative guards supplement the CLI's hard subprocess timeout."""

    max_fits: int
    max_seconds: int
    started: float
    fits: int = 0

    def check(self, *, fit: bool = False) -> None:
        if time.monotonic() - self.started >= self.max_seconds:
            raise TimeoutError("Experiment runtime budget exhausted; no artifact was promoted")
        if fit:
            if self.fits >= self.max_fits:
                raise RuntimeError("Experiment fit budget exhausted")
            self.fits += 1


def causal_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """All compared rows use the same causal availability and 336h warmup.

    An hourly prediction at t sees observed weather through t-1, as well as
    demand through t-1. A newly observed demand may be used by the next row:
    this is sequential one-step evaluation, never a fixed-origin long forecast.
    """
    weather_lagged = raw.asfreq("h").copy()
    weather_lagged[["Temperature", "Humidity"]] = (
        weather_lagged[["Temperature", "Humidity"]].ffill().shift(1)
    )
    frame = add_engineered_features(weather_lagged)
    columns = ["Demand", *IMPROVED_FEATURES]
    frame = frame.dropna(subset=columns)
    if frame.empty or not np.isfinite(frame[columns].to_numpy(dtype=float)).all():
        raise ValueError("Experiments require non-empty finite common feature/target rows")
    return frame


def metrics(actual: Any, predicted: Any) -> dict[str, float | None]:
    """Undefined R2 (constant groups) is JSON null, never NaN."""
    return {
        name: float(value) if np.isfinite(value) else None
        for name, value in calculate_metrics(actual, predicted).items()
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_sha256(path: Path) -> str:
    """Normalize Python source CRLF to LF; datasets, config and locks stay byte-exact."""
    content = path.read_bytes()
    if path.suffix == ".py":
        content = content.replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def provenance(config_path: Path, *, root: Path = ROOT) -> dict[str, Any]:
    files = sorted(
        {
            *root.glob("backend/experiments*.py"),
            root / "backend/features.py",
            root / "backend/ingestion.py",
            root / "backend/modeling.py",
            *root.glob("requirements*.lock.txt"),
            root / "requirements-research.txt",
        }
    )
    hashes = {
        path.relative_to(root).as_posix(): source_sha256(path) for path in files if path.is_file()
    }
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain=v1", "--untracked-files=no"], cwd=root, text=True
        ).splitlines()
    except (OSError, subprocess.CalledProcessError):
        revision, status = None, ["git provenance unavailable"]
    return {
        "git_revision": revision,
        "git_dirty": bool(status),
        "git_dirty_scope": "tracked repository files; new research sources are content-hashed below",
        "git_status": status,
        "data_path": "data/electricity_demand_2025.xlsx",
        "data_sha256": sha256(root / "data/electricity_demand_2025.xlsx"),
        "config_sha256": sha256(config_path),
        "source_and_lock_sha256": hashes,
        "hash_contract": "Python source CRLF normalized to LF; other files byte-exact SHA256",
        "source_manifest_sha256": hashlib.sha256(
            json.dumps(hashes, sort_keys=True).encode()
        ).hexdigest(),
        "dataset_provenance": "bundled_synthetic",
        "production_promotion": False,
    }


def verify_provenance(record: dict[str, Any], config_path: Path, *, root: Path = ROOT) -> None:
    """Refuse a success report if measured code, config, locks or data changed mid-run."""
    if record["data_sha256"] != sha256(root / "data/electricity_demand_2025.xlsx"):
        raise RuntimeError("Research dataset changed during execution")
    if record["config_sha256"] != sha256(config_path):
        raise RuntimeError("Experiment configuration changed during execution")
    for name, expected in record["source_and_lock_sha256"].items():
        path = root / name
        if not path.is_file() or source_sha256(path) != expected:
            raise RuntimeError(f"Research source or lock changed during execution: {name}")


def prepare_output(path: Path, *, root: Path = ROOT) -> Path:
    """Create a new report folder only under experiments/reports; reject overwrite."""
    output = path.resolve()
    reports = (root / "experiments/reports").resolve()
    if output == reports or not output.is_relative_to(reports):
        raise ValueError("Output must be a new child directory of experiments/reports")
    if output.exists():
        raise FileExistsError("Output directory already exists; choose a new run name")
    output.mkdir(parents=True)
    return output
