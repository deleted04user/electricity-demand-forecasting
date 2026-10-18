"""Failure/lifecycle regressions for explicit trusted forecasting resources."""

import copy
import json
import subprocess
import sys
from dataclasses import replace
from types import SimpleNamespace
from zoneinfo import ZoneInfoNotFoundError

import numpy as np
import pandas as pd
import pytest
from backend import artifacts
from backend.api_models import ModelPerformanceResponse
from backend.artifacts import (
    ArtifactError,
    Manifest,
    PackageMetadata,
    Period,
    load_model,
    publish_model_manifest,
)
from backend.main import create_app
from backend.service import ForecastError, ForecastService
from backend.settings import Settings
from fastapi.testclient import TestClient
from pydantic import ValidationError


@pytest.fixture(scope="module")
def loaded():
    active = ForecastService.load(Settings.from_env())
    yield active
    active.close()


def test_imports_do_not_load_resources_or_couple_evaluation_to_http():
    code = """
import joblib
import backend.ingestion as ingestion

def forbidden(*args, **kwargs):
    raise AssertionError('Resource loading at import')
joblib.load = forbidden
ingestion.load_hourly_data = forbidden
import backend.evaluate
import sys
assert 'backend.main' not in sys.modules
import backend.main
assert backend.main.app.state.runtime.service is None
"""
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)


def test_application_lifecycle_and_independent_states(loaded):
    first_service, second_service = copy.copy(loaded), copy.copy(loaded)
    first = create_app(service_factory=lambda settings: first_service)
    second = create_app(service_factory=lambda settings: second_service)
    with TestClient(first) as first_client, TestClient(second) as second_client:
        assert first_client.get("/api/live").json() == {"status": "alive"}
        assert first_client.get("/api/health").status_code == 200
        assert first.state.runtime is not second.state.runtime
        assert second_client.get("/api/meta").status_code == 200
    assert first_service.closed and second_service.closed
    assert first.state.runtime.service is None
    assert first_client.get("/api/health").status_code == 503
    assert not loaded.closed


def test_readiness_fails_safely_before_lifespan_and_after_initialization_failure():
    def broken(settings):
        raise FileNotFoundError("private filesystem path")

    application = create_app(service_factory=broken)
    client = TestClient(application)
    assert client.get("/api/health").json()["error_code"] == "not_initialized"
    with client:
        assert client.get("/api/live").status_code == 200
        for route in (
            "/api/health",
            "/api/overview",
            "/api/demand-analysis",
            "/api/model-performance",
            "/api/meta",
            "/api/forecast?date=2024-12-31&hour=12",
        ):
            response = client.get(route)
            assert response.status_code == 503
            assert response.json() == {
                "detail": "Forecast resources are unavailable",
                "status": "unavailable",
                "error_code": "resource_initialization_failed",
            }
        assert client.post("/api/forecast/future", json={"start": "2025-01-01"}).status_code == 503
        assert "private" not in client.get("/api/health").text
    assert application.state.runtime.error_code == "not_initialized"


def test_checksum_prevents_deserialization_of_replaced_pickle(tmp_path, loaded, monkeypatch):
    model = tmp_path / "replaced.pkl"
    model.write_bytes(b"not a trusted model")
    monkeypatch.setattr(
        artifacts.joblib, "load", lambda path: pytest.fail("Unverified pickle was loaded")
    )
    with pytest.raises(ArtifactError, match="checksum"):
        load_model(model, loaded.settings.manifest_path)


@pytest.mark.parametrize("resource", ["model_path", "manifest_path"])
def test_missing_resources_refuse_startup(tmp_path, loaded, resource):
    settings = replace(loaded.settings, **{resource: tmp_path / "missing"})
    with pytest.raises(ArtifactError, match="validation failed"):
        ForecastService(settings)


def test_missing_data_refuses_startup(tmp_path, loaded):
    with pytest.raises(FileNotFoundError):
        ForecastService(replace(loaded.settings, data_path=tmp_path / "missing.csv"))


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"model_sha256": "bad"},
        {"features": ["hour", "hour"]},
        {"features": [""]},
        {"extra": True},
    ],
)
def test_invalid_trust_manifest_is_rejected(loaded, change):
    manifest = json.loads(loaded.settings.manifest_path.read_text())
    with pytest.raises(ValidationError):
        Manifest.model_validate({**manifest, **change})


def test_runtime_compatibility_is_checked_before_deserialization(tmp_path, loaded, monkeypatch):
    manifest = json.loads(loaded.settings.manifest_path.read_text())
    manifest["xgboost_major_minor"] = "0.0"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    monkeypatch.setattr(
        artifacts.joblib, "load", lambda path: pytest.fail("Incompatible model was loaded")
    )
    with pytest.raises(ArtifactError, match="runtime"):
        load_model(loaded.settings.model_path, path)


@pytest.mark.parametrize("package", [[], {}, {"model": object()}])
def test_invalid_package_schema(loaded, monkeypatch, package):
    monkeypatch.setattr(artifacts.joblib, "load", lambda path: package)
    with pytest.raises(ArtifactError):
        load_model(loaded.settings.model_path, loaded.settings.manifest_path)


def test_feature_order_and_fitted_booster_must_agree(loaded, monkeypatch):
    package = {**loaded.package, "features": list(reversed(loaded.features))}
    monkeypatch.setattr(artifacts.joblib, "load", lambda path: package)
    with pytest.raises(ArtifactError, match="feature order"):
        load_model(loaded.settings.model_path, loaded.settings.manifest_path)
    package["features"] = loaded.features
    monkeypatch.setattr(
        loaded.model,
        "get_booster",
        lambda: SimpleNamespace(feature_names=list(reversed(loaded.features))),
    )
    with pytest.raises(ArtifactError, match="fitted booster"):
        load_model(loaded.settings.model_path, loaded.settings.manifest_path)


def test_model_type_and_nonfinite_metadata_are_rejected(loaded, monkeypatch):
    package = {**loaded.package, "model": object()}
    monkeypatch.setattr(artifacts.joblib, "load", lambda path: package)
    with pytest.raises(ArtifactError, match="XGBRegressor"):
        load_model(loaded.settings.model_path, loaded.settings.manifest_path)
    package["model"] = loaded.model
    package["metrics"] = {"mae": float("inf")}
    with pytest.raises(ArtifactError, match="ValidationError"):
        load_model(loaded.settings.model_path, loaded.settings.manifest_path)


@pytest.mark.parametrize(
    "start,end",
    [("NaT", "2024-01-01"), ("2024-01-02", "2024-01-01"), ("2024-01-01T00:00:00Z", "2024-01-02")],
)
def test_artifact_period_validation(start, end):
    with pytest.raises(ValidationError):
        Period(start=start, end=end)


def test_metadata_rejects_duplicate_features_wrong_importances_and_overlap(loaded):
    for change in (
        {"features": ["hour", "hour"]},
        {"feature_importance": {"unknown": 1}},
        {"training_period": loaded.package["test_period"]},
        {"early_stopping_period": loaded.package["test_period"]},
    ):
        with pytest.raises(ValidationError):
            PackageMetadata.model_validate({**loaded.package, **change})


def test_trusted_training_manifest_publication_is_atomic(tmp_path, loaded):
    path = tmp_path / "artifact-manifest.json"
    publish_model_manifest(loaded.settings.model_path, path, loaded.features)
    assert Manifest.model_validate_json(path.read_text()).model_sha256 == loaded.model_sha256
    assert not path.with_suffix(".json.tmp").exists()


def test_inputs_without_heldout_rows_are_unavailable(tmp_path, loaded):
    path = tmp_path / "short.csv"
    loaded.raw.iloc[:24].reset_index().to_csv(path, index=False)
    with pytest.raises(ArtifactError, match="held-out rows"):
        ForecastService(replace(loaded.settings, data_path=path))


def test_unknown_model_features_are_unavailable(loaded, monkeypatch):
    monkeypatch.setattr(
        "backend.service.load_model",
        lambda *args: SimpleNamespace(
            model=loaded.model,
            package=loaded.package,
            features=["missing_feature"],
            sha256=loaded.model_sha256,
        ),
    )
    with pytest.raises(ArtifactError, match="feature schema"):
        ForecastService(loaded.settings)


def test_nonfinite_model_predictions_are_unavailable(loaded, monkeypatch):
    class Nonfinite:
        def predict(self, features):
            return np.full(len(features), np.nan)

    monkeypatch.setattr(
        "backend.service.load_model",
        lambda *args: SimpleNamespace(
            model=Nonfinite(),
            package=loaded.package,
            features=loaded.features,
            sha256=loaded.model_sha256,
        ),
    )
    with pytest.raises(ArtifactError, match="predictions must be finite"):
        ForecastService(loaded.settings)
    active = copy.copy(loaded)
    active.model = Nonfinite()
    with pytest.raises(ForecastError, match="nonfinite_model_prediction"):
        active.forecast("2024-12-31", 12)
    with pytest.raises(ForecastError, match="nonfinite_model_prediction"):
        active.recursive_forecast(active.data, pd.Timestamp("2025-01-01"), 1)


def test_performance_requests_do_not_recompute_recursive_backtests(loaded, monkeypatch):
    active = copy.copy(loaded)
    monkeypatch.setattr(
        active, "recursive_forecast", lambda *args: pytest.fail("Request ran a recursive backtest")
    )
    with TestClient(create_app(service_factory=lambda settings: active)) as client:
        first = client.get("/api/model-performance")
        second = client.get("/api/model-performance")
        assert first.status_code == 200 and first.json() == second.json()


def test_diagnostics_snapshot_validates_identity_and_finite_schema(tmp_path, loaded, monkeypatch):
    path = tmp_path / "diagnostics.json"
    settings = replace(loaded.settings, diagnostics_path=path)
    active = copy.copy(loaded)
    active.settings = settings
    active.write_diagnostics()
    fresh = ForecastService(settings)
    monkeypatch.setattr(
        fresh,
        "_compute_horizon_evaluation",
        lambda: pytest.fail("Valid diagnostics were recomputed"),
    )
    fresh.warm_diagnostics()
    assert (
        fresh.model_performance()
        == ModelPerformanceResponse.model_validate(loaded.model_performance()).model_dump()
    )
    snapshot = json.loads(path.read_text())
    for change in ("identity", "nonfinite", "missing"):
        payload = copy.deepcopy(snapshot)
        if change == "identity":
            payload["identity"] = "stale"
        elif change == "nonfinite":
            payload["performance"]["metrics"]["mae"] = float("nan")
        else:
            payload.pop("performance")
        path.write_text(json.dumps(payload))
        fresh = ForecastService(settings)
        calls = []
        monkeypatch.setattr(
            fresh,
            "_compute_horizon_evaluation",
            lambda: calls.append(True) or loaded.horizon_evaluation(),
        )
        fresh.warm_diagnostics()
        assert calls == [True]


def test_cache_identity_changes_for_data_events_feature_code_and_timezone(
    tmp_path, loaded, monkeypatch
):
    data_path = tmp_path / "changed.csv"
    loaded.raw.reset_index().to_csv(data_path, index=False)
    first = ForecastService(replace(loaded.settings, data_path=data_path))
    data = pd.read_csv(data_path)
    data.loc[100, "Demand"] += 1
    data.to_csv(data_path, index=False)
    second = ForecastService(replace(loaded.settings, data_path=data_path))
    assert first.identity != second.identity
    assert first._identity() == first.identity
    changed = copy.copy(first)
    changed.events = {*first.events, pd.Timestamp("2024-01-07").date()}
    assert changed._identity() != first.identity
    changed = copy.copy(first)
    changed.settings = replace(first.settings, timezone="UTC")
    assert changed._identity() != first.identity
    changed = copy.copy(first)
    changed.features = list(reversed(first.features))
    assert changed._identity() != first.identity
    changed = copy.copy(first)
    changed.model_sha256 = "changed-model"
    assert changed._identity() != first.identity
    monkeypatch.setattr("backend.service.source_sha256", lambda path: "changed-code")
    assert first._identity() != first.identity
    assert first._performance_cache is None and second._performance_cache is None


def test_data_changed_while_loading_is_rejected(loaded, monkeypatch):
    identities = iter(["first-version", "second-version"])
    monkeypatch.setattr("backend.service.file_sha256", lambda path: next(identities))
    with pytest.raises(ArtifactError, match="Data changed during initialization"):
        ForecastService(loaded.settings)


def test_closed_or_unwarmed_services_cannot_serve_diagnostics(loaded):
    active = copy.copy(loaded)
    active.close()
    for function in (active.model_performance, active.horizon_evaluation):
        with pytest.raises(RuntimeError, match="not been initialized"):
            function()


def test_settings_capture_environment_and_validate_timezone(tmp_path, monkeypatch):
    monkeypatch.setenv("ELECTRICITY_TIMEZONE", "UTC")
    monkeypatch.setenv("CORS_ORIGINS", "http://a.example, , http://b.example")
    first = Settings.from_env(tmp_path)
    monkeypatch.setenv("ELECTRICITY_TIMEZONE", "Africa/Casablanca")
    second = Settings.from_env(tmp_path)
    assert first.timezone == "UTC" and second.timezone == "Africa/Casablanca"
    assert first.cors_origins == ("http://a.example", "http://b.example")
    assert first.bundled_data_path == tmp_path / "data/electricity_demand_2025.xlsx"
    with pytest.raises(ZoneInfoNotFoundError):
        replace(first, timezone="invalid-zone")


def test_constant_weather_and_missing_days_remain_valid_json(loaded):
    active = copy.copy(loaded)
    active.data = loaded.data.copy()
    active.data[["Temperature", "Humidity"]] = [20.0, 50.0]
    missing_day = active.data.index.normalize() == pd.Timestamp("2024-06-01")
    active.data.loc[missing_day, "Demand"] = np.nan
    active.raw = active.data[["Demand", "Temperature", "Humidity"]].copy()
    active._performance_cache = active._compute_model_performance()
    with TestClient(create_app(service_factory=lambda settings: active)) as client:
        analysis = client.get("/api/demand-analysis")
        assert analysis.status_code == 200
        assert any(
            value is None
            for row in analysis.json()["correlation_matrix"]["values"]
            for value in row
        )
        overview = client.get("/api/overview")
        performance = client.get("/api/model-performance")
        assert overview.status_code == 200 and performance.status_code == 200
        assert "2024-06-01" not in {row["date"] for row in overview.json()["demand_timeseries"]}
        assert "2024-06-01" not in {
            row["date"] for row in performance.json()["actual_vs_predicted"]
        }
        assert client.get("/api/meta").json()["data_quality"]["missing"]["demand"] == int(
            (loaded.data["Demand"].isna() | missing_day).sum()
        )
        assert client.get("/api/meta").json()["data_quality"]["model_data_compatible"] is False


def test_source_identity_normalizes_windows_line_endings(tmp_path):
    lf, crlf = tmp_path / "lf.py", tmp_path / "crlf.py"
    lf.write_bytes(b"def function():\n    return 1\n")
    crlf.write_bytes(b"def function():\r\n    return 1\r\n")
    assert artifacts.source_sha256(lf) == artifacts.source_sha256(crlf)


@pytest.mark.parametrize("shape", ["scalar", "matrix", "wrong_length"])
def test_bootstrap_rejects_wrong_prediction_shape(loaded, monkeypatch, shape):
    class BadShape:
        def predict(self, features):
            if shape == "scalar":
                return np.array(1.0)
            if shape == "matrix":
                return np.ones((len(features), 1))
            return np.ones(len(features) - 1)

    monkeypatch.setattr(
        "backend.service.load_model",
        lambda *args: SimpleNamespace(
            model=BadShape(),
            package=loaded.package,
            features=loaded.features,
            sha256=loaded.model_sha256,
        ),
    )
    with pytest.raises(ArtifactError, match="match the input rows"):
        ForecastService(loaded.settings)


def test_warmup_failure_closes_owned_resources(loaded, monkeypatch):
    active = copy.copy(loaded)
    monkeypatch.setattr(ForecastService, "__new__", lambda cls, settings: active)
    monkeypatch.setattr(ForecastService, "__init__", lambda *args: None)
    monkeypatch.setattr(
        active, "warm_diagnostics", lambda: (_ for _ in ()).throw(ValueError("bad diagnostics"))
    )
    with pytest.raises(ValueError, match="bad diagnostics"):
        ForecastService.load(loaded.settings)
    assert active.closed
