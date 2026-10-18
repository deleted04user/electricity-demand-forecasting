"""Exercise selection and artifact promotion with deterministic, tiny estimators."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from backend import modeling


class FakeDemandModel:
    feature_importances_ = np.array([1.0])
    best_iteration = 2

    def __init__(self, offset=0):
        self.offset = offset
        self.fit_calls = []

    def predict(self, features):
        return features["signal"].to_numpy() + self.offset

    def fit(self, features, target, **kwargs):
        self.fit_calls.append((features.copy(), target.copy(), kwargs))
        return self


def training_frame():
    index = pd.to_datetime(
        [
            "2022-12-30",
            "2022-12-31",
            "2023-01-01",
            "2023-04-30",
            "2023-05-01",
            "2023-08-31",
            "2023-09-01",
            "2023-12-31",
            "2024-01-01",
            "2024-01-02",
        ]
    )
    signal = np.arange(len(index), dtype=float) + 100
    return pd.DataFrame(
        {
            "signal": signal,
            "Demand": signal,
            "demand_lag_24h": signal - 3,
            "demand_lag_168h": signal - 7,
        },
        index=index,
    )


def test_configuration_selection_uses_validation_before_holdout(monkeypatch):
    candidates = (
        modeling.Candidate("worse", ("signal",), {"offset": 10}),
        modeling.Candidate("better", ("signal",), {"offset": 0}),
    )
    estimators = []

    def make_model(params, *, early_stopping):
        assert early_stopping
        model = FakeDemandModel(params["offset"])
        estimators.append(model)
        return model

    monkeypatch.setattr(modeling, "CANDIDATES", candidates)
    monkeypatch.setattr(modeling, "_xgb_model", make_model)
    winner, results = modeling.select_configuration(training_frame())
    assert winner.name == "better" and len(results) == 2
    assert len(estimators) == 6
    for estimator in estimators:
        features, _, kwargs = estimator.fit_calls[0]
        validation, _ = kwargs["eval_set"][0]
        assert features.index.max() < validation.index.min()
        assert validation.index.max() < modeling.TEST_START


def test_final_fit_freezes_early_stopping_before_combining_pretest_rows(monkeypatch):
    calls = []

    def make_model(params, *, early_stopping):
        estimator = FakeDemandModel()
        calls.append((params, early_stopping, estimator))
        return estimator

    monkeypatch.setattr(modeling, "_xgb_model", make_model)
    candidate = modeling.Candidate("selected", ("signal",), {"n_estimators": 50})
    data = training_frame().loc[:"2023-12-31"]
    model, params = modeling._fit_selected(data, candidate)
    assert params["n_estimators"] == 3
    assert calls[0][1] is True and calls[1][1] is False
    assert model is calls[1][2]
    assert model.fit_calls[0][0].index.equals(data.index)
    assert "eval_set" not in model.fit_calls[0][2]


@pytest.mark.parametrize("offset, promoted", [(0, True), (10, False)])
def test_training_preserves_or_promotes_with_backup_and_honest_provenance(
    tmp_path, monkeypatch, offset, promoted
):
    root = tmp_path / "repo"

    class FrozenClock:
        @staticmethod
        def now(tz):
            return datetime(2026, 10, 17, tzinfo=UTC)

    monkeypatch.setattr(modeling, "datetime", FrozenClock)
    model_path = root / "models/active.pkl"
    model_path.parent.mkdir(parents=True)
    source = tmp_path / "verified.csv"
    source.write_text("verified local feed\n", encoding="utf-8")
    joblib.dump({"model": FakeDemandModel(5), "features": ["signal"]}, model_path)
    original_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    data = training_frame()
    candidate = modeling.Candidate("selected", ("signal",), {"n_estimators": 3})

    def select(pretest):
        assert pretest.index.max() < modeling.TEST_START
        return candidate, [{"name": "selected", "average_validation_metrics": {"wape": 1}}]

    def fit(pretest, winner):
        assert pretest.index.max() < modeling.TEST_START and winner is candidate
        return FakeDemandModel(offset), candidate.params

    monkeypatch.setattr(modeling, "ROOT", root)
    monkeypatch.setattr(modeling, "ACTIVE_MODEL_PATH", model_path)
    monkeypatch.setattr(modeling, "load_hourly_data", lambda path: data)
    monkeypatch.setattr(modeling, "add_engineered_features", lambda raw: raw)
    monkeypatch.setattr(modeling, "select_configuration", select)
    monkeypatch.setattr(modeling, "_fit_selected", fit)
    report = modeling.run_training(source)
    assert report["synthetic_data"] is None and report["test_rows"] == 2
    assert report["data_provenance"] == "caller_supplied_unverified"
    assert report["data_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    retained = joblib.load(root / report["candidate_path"])
    assert retained["synthetic_data"] is None
    assert retained["data_provenance"] == "caller_supplied_unverified"
    assert retained["selection"]["winner"] == "selected"
    saved_report = json.loads(
        next((root / "models/candidates").glob("evaluation_*.json")).read_text()
    )
    assert saved_report["outcome"] == report["outcome"]
    if promoted:
        assert report["outcome"] == "improved_model_deployed"
        assert (
            hashlib.sha256((root / report["backup_path"]).read_bytes()).hexdigest() == original_hash
        )
        assert joblib.load(model_path)["model"].offset == offset
        manifest = json.loads((root / "models/artifact-manifest.json").read_text())
        assert manifest["model_sha256"] == hashlib.sha256(model_path.read_bytes()).hexdigest()
        assert manifest["features"] == ["signal"]
        assert not model_path.with_name(model_path.name + ".tmp").exists()
    else:
        assert report["outcome"] == "candidate_retained" and report["backup_path"] is None
        assert hashlib.sha256(model_path.read_bytes()).hexdigest() == original_hash

    second = modeling.run_training(source)
    assert second["candidate_path"] != report["candidate_path"]
    assert len(list((root / "models/candidates").glob("evaluation_*.json"))) == 2


def test_synthetic_guard_cannot_be_bypassed_with_relative_path(monkeypatch):
    monkeypatch.chdir(modeling.ROOT)
    for path in (None, Path("data/electricity_demand_2025.xlsx"), modeling.DATA_PATH):
        with pytest.raises(RuntimeError, match="bundled synthetic"):
            modeling.run_training(path)


def test_manifest_publication_failure_restores_the_previous_active_model(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    model_path = root / "models/active.pkl"
    model_path.parent.mkdir(parents=True)
    source = tmp_path / "local.csv"
    source.write_text("caller supplied data\n", encoding="utf-8")
    joblib.dump({"model": FakeDemandModel(5), "features": ["signal"]}, model_path)
    previous = model_path.read_bytes()
    manifest = root / "models/artifact-manifest.json"
    manifest.write_text('{"original": true}', encoding="utf-8")
    candidate = modeling.Candidate("selected", ("signal",), {"n_estimators": 3})
    monkeypatch.setattr(modeling, "ROOT", root)
    monkeypatch.setattr(modeling, "ACTIVE_MODEL_PATH", model_path)
    monkeypatch.setattr(modeling, "load_hourly_data", lambda path: training_frame())
    monkeypatch.setattr(modeling, "add_engineered_features", lambda frame: frame)
    monkeypatch.setattr(modeling, "select_configuration", lambda frame: (candidate, []))
    monkeypatch.setattr(modeling, "_fit_selected", lambda frame, winner: (FakeDemandModel(), {}))

    def fail_publication(*args):
        raise OSError("manifest cannot be published")

    monkeypatch.setattr(modeling, "publish_model_manifest", fail_publication)
    with pytest.raises(OSError, match="manifest cannot be published"):
        modeling.run_training(source)
    assert model_path.read_bytes() == previous
    assert json.loads(manifest.read_text()) == {"original": True}
    assert not model_path.with_name("active.pkl.tmp").exists()


def test_synthetic_guard_rejects_renamed_copy_before_training(tmp_path, monkeypatch):
    copied = tmp_path / "claimed_verified.xlsx"
    copied.write_bytes(modeling.DATA_PATH.read_bytes())

    def reject_training(path):
        pytest.fail("The known synthetic sample must be rejected before data loading or training")

    monkeypatch.setattr(modeling, "load_hourly_data", reject_training)
    with pytest.raises(RuntimeError, match="bundled synthetic"):
        modeling.run_training(copied)


@pytest.mark.parametrize(
    "actual,predicted,message",
    [
        ([], [], "non-empty"),
        ([1], [1, 2], "identical shapes"),
        ([np.nan], [1], "finite"),
        ([1], [np.inf], "finite"),
        ([0, 0], [1, 1], "undefined"),
    ],
)
def test_metrics_reject_undefined_inputs(actual, predicted, message):
    with pytest.raises(ValueError, match=message):
        modeling.calculate_metrics(actual, predicted)


def test_rolling_folds_reject_missing_training_or_validation():
    with pytest.raises(ValueError, match="Invalid or empty rolling fold"):
        modeling.rolling_origin_splits(training_frame().loc["2024-01-01":])


@pytest.mark.parametrize("arguments", [[], ["--train"]])
def test_training_cli_requires_explicit_action_and_real_data(monkeypatch, arguments):
    monkeypatch.setattr("sys.argv", ["modeling", *arguments])
    with pytest.raises(SystemExit) as exc:
        modeling.main()
    assert exc.value.code == 2
