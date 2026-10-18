"""Missing diagnostics and extreme weather must not defeat controlled API responses."""

import copy
import hashlib
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from backend import evaluate
from backend.api_models import HorizonMetrics
from backend.diagnostics import horizons
from backend.main import create_app
from backend.service import ForecastService
from backend.settings import Settings
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def service():
    active = ForecastService.load(Settings.from_env())
    yield active
    active.close()


@pytest.mark.parametrize("temperature", [1e308, 1e20])
def test_future_rejects_engineered_overflow_before_predicting(service, monkeypatch, temperature):
    active = copy.copy(service)
    monkeypatch.setattr(
        active.model, "predict", lambda frame: pytest.fail("Invalid features reached XGBoost")
    )
    start = str(active.data.index.max() + pd.Timedelta(hours=1))
    with TestClient(create_app(service_factory=lambda settings: active)) as client:
        response = client.post(
            "/api/forecast/future",
            json={"start": start, "horizon": 1, "temperature": [temperature], "humidity": [50]},
        )
        assert response.status_code == 400
        assert response.json() == {
            "detail": "Forecast features must be finite and representable as float32"
        }


@pytest.mark.parametrize("all_origin_targets_missing", [False, True])
def test_horizons_keep_missing_targets_as_unavailable_metrics(
    service, monkeypatch, all_origin_targets_missing
):
    active = copy.copy(service)
    active.data = service.data.copy()
    for start in (
        pd.Timestamp(active.test_start) + pd.Timedelta(days=31),
        pd.Timestamp(active.test_start) + pd.Timedelta(days=213),
    ):
        missing = pd.date_range(start, periods=168 if all_origin_targets_missing else 6, freq="h")
        active.data.loc[missing, "Demand"] = np.nan
    monkeypatch.setattr(
        active,
        "recursive_forecast",
        lambda history, start, horizon: [{"predicted": 3000.0}] * horizon,
    )
    result = horizons(active)
    validated = HorizonMetrics.model_validate(result).model_dump()
    empty = validated["recursive_multi_step"]["1"]
    assert empty["origins"] == 2 and empty["scored_rows"] == 0
    assert empty["metrics"] == {"mae": None, "rmse": None, "r2": None, "wape": None, "bias": None}
    if all_origin_targets_missing:
        assert all(row["scored_rows"] == 0 for row in validated["recursive_multi_step"].values())
    else:
        assert validated["recursive_multi_step"]["24"]["scored_rows"] > 0
        assert validated["recursive_multi_step"]["24"]["metrics"]["mae"] is not None
    active._horizon_cache = result
    active._performance_cache = active._compute_model_performance()
    with TestClient(create_app(service_factory=lambda settings: active)) as client:
        assert client.get("/api/health").status_code == 200
        body = client.get("/api/model-performance").json()
        assert body["horizon_metrics"]["recursive_multi_step"]["1"]["scored_rows"] == 0


def manifest_service(tmp_path):
    root = tmp_path / "repo"
    (root / "models").mkdir(parents=True)
    data_path = root / "external.csv"
    data_path.write_bytes(b"loaded evaluation data")
    model_path = root / "models/model.pkl"
    model_path.write_bytes(b"trusted model fixture")
    return SimpleNamespace(
        settings=replace(Settings.from_env(root), data_path=data_path, model_path=model_path),
        data_sha256=hashlib.sha256(data_path.read_bytes()).hexdigest(),
        model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
        identity="frozen-inputs",
        model=SimpleNamespace(get_params=lambda: {"max_depth": 2}),
        package={
            "training_date": "2025-01-01",
            "training_period": {"start": "2020-01-15", "end": "2023-12-31"},
            "early_stopping_period": {"start": "2023-01-01", "end": "2023-12-31"},
            "test_period": {"start": "2024-01-01", "end": "2024-12-31"},
            "metrics": {"MAE": 1},
        },
        data=pd.DataFrame(
            {"Demand": [100, 200], "signal": [1, 2]},
            index=pd.to_datetime(["2022-06-01", "2024-12-31"]),
        ),
        features=["signal"],
        model_performance=lambda: {"metrics": {"mae": 1}, "baselines": {}},
    )


def test_manifest_preserves_fixed_artifact_training_metadata(tmp_path, monkeypatch):
    active = manifest_service(tmp_path)
    original_period = active.package["training_period"].copy()
    monkeypatch.setattr(evaluate, "latest_promotion_summary", lambda root: None)
    monkeypatch.setattr(evaluate, "backtest", lambda service: [])
    report = evaluate.manifest(active)
    assert report["training_period"] == original_period
    assert active.package["training_period"] == original_period
    assert report["evaluation_data_coverage"] == {
        "start": "2022-06-01 00:00:00",
        "end": "2024-12-31 00:00:00",
    }
    assert report["data_sha256"] == active.data_sha256


@pytest.mark.parametrize("when", ["before", "during"])
def test_manifest_refuses_changed_input_bytes(tmp_path, monkeypatch, when):
    active = manifest_service(tmp_path)
    monkeypatch.setattr(evaluate, "latest_promotion_summary", lambda root: None)
    if when == "before":
        active.settings.data_path.write_bytes(b"different feed after initialization")
        monkeypatch.setattr(
            evaluate, "backtest", lambda service: pytest.fail("Changed data reached backtest")
        )
    else:

        def mutate(service):
            service.settings.data_path.write_bytes(b"changed while evaluating")
            return []

        monkeypatch.setattr(evaluate, "backtest", mutate)
    with pytest.raises(ValueError, match="Evaluation data changed"):
        evaluate.manifest(active)
    assert not (active.settings.root / "models/metadata.json").exists()
