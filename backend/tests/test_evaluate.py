import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd
from backend import evaluate
from backend.settings import Settings


class ManifestModel:
    def get_params(self):
        return {"n_estimators": 3}


def test_manifest_supports_external_local_data_without_mislabeling_it(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "models").mkdir(parents=True)
    model_path = root / "models/model.pkl"
    model_path.write_bytes(b"test model")
    data_path = tmp_path / "operational.csv"
    data_path.write_text("test operational feed", encoding="utf-8")
    package = {
        "training_date": "2025-01-01",
        "training_period": {"start": "2022-01-01", "end": "2023-12-31"},
        "early_stopping_period": {"start": "2023-01-01", "end": "2023-12-31"},
        "test_period": {"start": "2024-01-01", "end": "2024-12-31"},
        "metrics": {"WAPE": 1},
    }
    data = pd.DataFrame(
        {"Demand": [100, 110], "signal": [1, 2]}, index=pd.to_datetime(["2022-01-01", "2023-01-01"])
    )
    service = SimpleNamespace(
        settings=replace(Settings.from_env(root), data_path=data_path, model_path=model_path),
        package=package,
        data=data,
        features=["signal"],
        model=ManifestModel(),
        identity="test-identity",
        model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
        data_sha256=hashlib.sha256(data_path.read_bytes()).hexdigest(),
        model_performance=lambda: {"metrics": {"wape": 1}, "baselines": {}},
    )
    monkeypatch.setattr(evaluate, "latest_promotion_summary", lambda root: None)
    monkeypatch.setattr(evaluate, "backtest", lambda service: [])
    result = evaluate.manifest(service)
    assert result["data_filename"] == str(data_path)
    assert result["synthetic_data"] is None
    assert result["data_provenance"] == "caller_supplied_unverified"
    assert result["data_sha256"] == hashlib.sha256(data_path.read_bytes()).hexdigest()
    assert result["model_parameters"] == {"n_estimators": 3}
    assert json.loads((root / "models/metadata.json").read_text())["data_filename"] == str(
        data_path
    )


def test_promotion_summary_handles_missing_and_recorded_reports(tmp_path):
    assert evaluate.latest_promotion_summary(tmp_path) is None
    candidates = tmp_path / "models/candidates"
    candidates.mkdir(parents=True)
    report = {
        "outcome": "candidate_retained",
        "selected_candidate": "winner",
        "candidate_path": "models/candidate.pkl",
        "backup_path": None,
        "test_rows": 10,
        "metrics": {"new XGBoost": {"wape": 2}},
        "validation_results": [{"name": "winner", "average_validation_metrics": {"wape": 3}}],
    }
    (candidates / "evaluation_test.json").write_text(json.dumps(report), encoding="utf-8")
    result = evaluate.latest_promotion_summary(tmp_path)
    assert result["selected_candidate"] == "winner"
    assert result["rolling_validation_metrics"]["wape"] == 3
    assert result["held_out_comparison"] == report["metrics"]


def test_backtest_never_exposes_postcutoff_inputs_to_forecaster():
    index = pd.date_range("2024-04-01", periods=24, freq="h").append(
        pd.date_range("2024-10-01", periods=24, freq="h")
    )
    data = pd.DataFrame({"Demand": np.tile(np.arange(24) + 100, 2)}, index=index)

    def forecast(history, start, horizon):
        assert history.empty or history.index.max() < start
        assert horizon == 24
        return [{"predicted": float(100 + hour)} for hour in range(horizon)]

    results = evaluate.backtest(SimpleNamespace(data=data, recursive_forecast=forecast))
    assert len(results) == 2 and all(row["metrics"]["wape"] == 0 for row in results)
