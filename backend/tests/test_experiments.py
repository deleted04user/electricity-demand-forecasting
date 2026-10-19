"""Meaningful research protocol, causal availability and report regressions."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from backend import experiments as runner
from backend import experiments_analysis as analysis
from backend import experiments_protocol as protocol


@pytest.fixture
def raw():
    index = pd.date_range("2022-01-01", "2024-12-31 23:00:00", freq="h")
    t = np.arange(len(index))
    return pd.DataFrame(
        {
            "Demand": 2000 + 250 * np.sin(t / 24) + 0.01 * t,
            "Temperature": 20 + np.sin(t / 72),
            "Humidity": 50 + np.cos(t / 24),
        },
        index=index,
    )


def budget():
    return protocol.Budget(28, 300, time.monotonic())


def write_config(tmp_path, config):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("group", "name", "value"),
    [
        (None, "dataset", "https://example.com/remote.csv"),
        (None, "purpose", "production"),
        (None, "folds", ["2024"]),
        (None, "selection", "test_wape"),
        (None, "initial_seed", 99),
        (None, "repeat_variants", ["lags_weather"]),
        (None, "unknown", 1),
        ("budget", "max_fits", 27),
        ("budget", "max_fits", 29),
        ("budget", "max_seconds", 301),
        ("budget", "max_seconds", 0),
        ("budget", "threads", 3),
        ("budget", "threads", True),
        ("budget", "unknown", 1),
        ("parameters", "n_estimators", 121),
        ("parameters", "n_estimators", 1.5),
        ("parameters", "max_depth", 12),
        ("parameters", "unknown", "code"),
        ("historical_diagnostics", "nominal_coverage", 0.95),
    ],
)
def test_protocol_rejects_leakage_and_unbounded_or_unknown_config(tmp_path, group, name, value):
    config = protocol.load_config()
    target = config if group is None else config[group]
    target[name] = value
    with pytest.raises(ValueError):
        protocol.load_config(write_config(tmp_path, config))


def test_protocol_declares_28_fits_and_can_lower_only_resource_caps(tmp_path):
    config = protocol.load_config()
    assert protocol.planned_fits(config) == 28
    config["parameters"]["n_estimators"] = 2
    config["budget"].update(threads=1, max_seconds=30)
    assert protocol.load_config(write_config(tmp_path, config)) == config
    for name in ("budget", "parameters"):
        broken = copy.deepcopy(config)
        broken[name] = []
        with pytest.raises(ValueError):
            protocol.load_config(write_config(tmp_path, broken))


def test_budget_stops_before_extra_fit_and_after_deadline(monkeypatch):
    limit = protocol.Budget(1, 10, 100)
    monkeypatch.setattr(protocol.time, "monotonic", lambda: 101)
    limit.check(fit=True)
    assert limit.fits == 1
    with pytest.raises(RuntimeError, match="fit budget"):
        limit.check(fit=True)
    monkeypatch.setattr(protocol.time, "monotonic", lambda: 110)
    with pytest.raises(TimeoutError, match="runtime"):
        limit.check()


def test_common_rows_and_past_weather_are_identical_across_variants(raw):
    frame = protocol.causal_frame(raw)
    stamp = pd.Timestamp("2023-05-01")
    assert frame.at[stamp, "Temperature"] == raw.at[stamp - pd.Timedelta(hours=1), "Temperature"]
    assert frame.at[stamp, "demand_lag_1h"] == raw.at[stamp - pd.Timedelta(hours=1), "Demand"]
    changed = raw.copy()
    changed.loc[stamp:, ["Demand", "Temperature", "Humidity"]] *= 10
    altered = protocol.causal_frame(changed)
    pd.testing.assert_series_equal(
        frame.loc[stamp, list(protocol.FEATURE_GROUPS["full"])],
        altered.loc[stamp, list(protocol.FEATURE_GROUPS["full"])],
    )
    for features in protocol.FEATURE_GROUPS.values():
        assert frame[list(features)].notna().all().all()
        assert len(frame[list(features)]) == len(frame)
    broken = raw.copy()
    broken.loc[stamp, "Demand"] = np.inf
    with pytest.raises(ValueError, match="finite"):
        protocol.causal_frame(broken)
    with pytest.raises(ValueError, match="non-empty"):
        protocol.causal_frame(raw.head(300))


def test_json_metrics_use_null_for_undefined_r2_and_reject_nonfinite():
    result = protocol.metrics([2, 2], [1, 3])
    assert result["r2"] is None
    assert "NaN" not in json.dumps(result, allow_nan=False)
    with pytest.raises(ValueError, match="finite"):
        protocol.metrics([1, 2], [1, np.nan])


def test_output_guard_never_overwrites_source_model_or_prior_reports(tmp_path):
    active = tmp_path / "models/model.pkl"
    active.parent.mkdir()
    active.write_bytes(b"active")
    for path in (active, active.parent, tmp_path, tmp_path / "experiments/reports"):
        with pytest.raises(ValueError):
            protocol.prepare_output(path, root=tmp_path)
    report = protocol.prepare_output(tmp_path / "experiments/reports/new", root=tmp_path)
    assert report.is_dir()
    with pytest.raises(FileExistsError):
        protocol.prepare_output(report, root=tmp_path)
    assert active.read_bytes() == b"active"


def test_provenance_is_portable_and_changes_with_source_not_user_file(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/electricity_demand_2025.xlsx").write_bytes(b"data")
    (tmp_path / "backend").mkdir()
    source = tmp_path / "backend/experiments.py"
    source.write_text("code", encoding="utf-8")
    config = write_config(tmp_path, protocol.load_config())
    monkeypatch.setattr(
        protocol.subprocess,
        "check_output",
        lambda args, **kwargs: "abc123\n" if "rev-parse" in args else " M backend/experiments.py\n",
    )
    first = protocol.provenance(config, root=tmp_path)
    assert first["git_dirty"] is True
    protocol.verify_provenance(first, config, root=tmp_path)
    assert all(not Path(name).is_absolute() for name in first["source_and_lock_sha256"])
    (tmp_path / "private.txt").write_text("unrelated user content", encoding="utf-8")
    assert (
        first["source_manifest_sha256"]
        == protocol.provenance(config, root=tmp_path)["source_manifest_sha256"]
    )
    source.write_text("changed", encoding="utf-8")
    with pytest.raises(RuntimeError, match="source or lock changed"):
        protocol.verify_provenance(first, config, root=tmp_path)
    assert (
        first["source_manifest_sha256"]
        != protocol.provenance(config, root=tmp_path)["source_manifest_sha256"]
    )

    def fail(*args, **kwargs):
        raise OSError("no git")

    monkeypatch.setattr(protocol.subprocess, "check_output", fail)
    assert protocol.provenance(config, root=tmp_path)["git_revision"] is None


@pytest.mark.parametrize("filename", ["uv.lock", "pyproject.toml"])
def test_research_rejects_native_dependency_manifest_changes(tmp_path, monkeypatch, filename):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/electricity_demand_2025.xlsx").write_bytes(b"data")
    manifest = tmp_path / filename
    manifest.write_text("original", encoding="utf-8")
    config = write_config(tmp_path, protocol.load_config())
    monkeypatch.setattr(protocol.subprocess, "check_output", lambda *args, **kwargs: "")
    record = protocol.provenance(config, root=tmp_path)
    assert record["source_and_lock_sha256"][filename] == protocol.sha256(manifest)
    manifest.write_text("changed", encoding="utf-8")
    with pytest.raises(RuntimeError, match="source or lock changed"):
        protocol.verify_provenance(record, config, root=tmp_path)


def test_source_hash_normalizes_only_python_newlines_and_detects_config_data_changes(tmp_path):
    script = tmp_path / "test.py"
    script.write_bytes(b"first\r\nsecond\r\n")
    normalized = protocol.source_sha256(script)
    script.write_bytes(b"first\nsecond\n")
    assert protocol.source_sha256(script) == normalized
    lock = tmp_path / "requirements.lock.txt"
    lock.write_bytes(b"package\r\n")
    assert protocol.source_sha256(lock) == protocol.sha256(lock)
    (tmp_path / "data").mkdir()
    data = tmp_path / "data/electricity_demand_2025.xlsx"
    data.write_bytes(b"data")
    cfg = write_config(tmp_path, protocol.load_config())
    record = {
        "data_sha256": protocol.sha256(data),
        "config_sha256": protocol.sha256(cfg),
        "source_and_lock_sha256": {},
    }
    cfg.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="configuration"):
        protocol.verify_provenance(record, cfg, root=tmp_path)
    data.write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="dataset"):
        protocol.verify_provenance(record, cfg, root=tmp_path)


def test_selection_ignores_repeat_seeds_and_baseline_and_requires_finite_complete_input():
    rows = [
        {"variant": name, "seed": 42, "mean_fold_wape": 10 + i, "mean_fold_rmse": 100}
        for i, name in enumerate(protocol.FEATURE_GROUPS)
    ]
    rows += [
        {"variant": "full", "seed": 43, "mean_fold_wape": 0, "mean_fold_rmse": 0},
        {"variant": "naive24", "seed": 42, "mean_fold_wape": 0, "mean_fold_rmse": 0},
    ]
    assert runner.select_variant(rows) == "lags"
    with pytest.raises(ValueError):
        runner.select_variant(rows[1:])
    rows[0]["mean_fold_wape"] = np.nan
    with pytest.raises(ValueError, match="finite"):
        runner.select_variant(rows)


class LagModel:
    def __init__(self, value=None):
        self.rows = []
        self.value = value

    def predict(self, frame):
        self.rows.append(frame.copy())
        if self.value is not None:
            return np.full(len(frame), self.value)
        return frame["demand_lag_1h"].to_numpy() + 0.25


def test_recursive_uses_predicted_demand_and_no_future_measured_weather_or_demand(raw):
    origin = pd.Timestamp("2024-01-01")
    model = LagModel()
    predicted = analysis.recursive_predictions(
        model, protocol.FEATURE_GROUPS["full"], raw, origin, 6, budget()
    )
    assert np.isclose(predicted[1] - predicted[0], 0.25)
    assert (
        model.rows[0].iloc[0]["Temperature"]
        == raw.at[origin - pd.Timedelta(hours=1), "Temperature"]
    )
    changed = raw.copy()
    changed.loc[origin:, :] = 999999
    np.testing.assert_array_equal(
        predicted,
        analysis.recursive_predictions(
            LagModel(), protocol.FEATURE_GROUPS["full"], changed, origin, 6, budget()
        ),
    )
    with pytest.raises(ValueError, match="337 complete"):
        analysis.recursive_predictions(model, ("demand_lag_1h",), raw.tail(10), origin, 1, budget())
    for horizon in (0, 169):
        with pytest.raises(ValueError, match="horizon"):
            analysis.recursive_predictions(
                model, ("demand_lag_1h",), raw, origin, horizon, budget()
            )
    for invalid in (-1, np.inf, np.nan):
        with pytest.raises(ValueError, match="Invalid recursive prediction"):
            analysis.recursive_predictions(
                LagModel(invalid), ("demand_lag_1h",), raw, origin, 1, budget()
            )


def test_recursive_calendar_boundary_uses_only_available_hourly_weather(raw):
    # All history is December, so January weather must fall back to prior hourly averages.
    history = raw.loc["2023-12-01":"2023-12-31 23:00:00"]
    assert (
        len(
            analysis.recursive_predictions(
                LagModel(), ("demand_lag_1h",), history, pd.Timestamp("2024-01-01"), 2, budget()
            )
        )
        == 2
    )


def test_segment_counts_partition_data_and_bands_use_training_quantiles(raw):
    frame = raw.loc["2024-01-01":"2024-01-07 23:00:00"]
    rows = analysis.segmented_errors(
        frame, frame["Demand"].to_numpy() + 10, pd.Series([0.0, 10.0, 20.0, 30.0])
    )
    for dimension in ("month", "hour", "weekend", "demand_band"):
        groups = [row for row in rows if row["dimension"] == dimension]
        assert sum(row["rows"] for row in groups) == len(frame)
        assert all(np.isclose(row["mae"], 10) for row in groups)
    assert [row["segment"] for row in rows if row["dimension"] == "demand_band"] == ["high"]
    with pytest.raises(ValueError, match="match"):
        analysis.segmented_errors(frame, np.array([1]), pd.Series([1, 2]))


def test_interval_radius_is_from_supplied_calibration_not_future_targets(raw, monkeypatch):
    monkeypatch.setattr(analysis, "recursive_predictions", lambda *args: np.full(168, 2000.0))
    cfg = protocol.load_config()["historical_diagnostics"]
    rows, summary = analysis.interval_diagnostics(None, (), raw, np.arange(10.0), cfg, budget())
    assert len(rows) == 60
    assert all(row["origins"] == 12 and row["calibration_radius_mw"] == 9 for row in summary)
    assert [row["horizon_hours"] for row in summary] == [1, 6, 24, 72, 168]
    assert summary[1]["mean_width_mw"] > summary[0]["mean_width_mw"]
    # Mixed missing targets and NumPy bools must not produce object-dtype OR sums.
    all_covered = raw.copy()
    all_covered["Demand"] = 2000.0
    all_covered.loc[pd.Timestamp("2024-01-01"), "Demand"] = np.nan
    _, full_coverage = analysis.interval_diagnostics(
        None, (), all_covered, np.arange(10.0), cfg, budget()
    )
    assert full_coverage[0]["origins"] == 11
    assert all(row["empirical_coverage"] == 1.0 for row in full_coverage)
    all_covered.loc[pd.Timestamp("2024-02-01"), "Demand"] = 3000.0
    _, partial_coverage = analysis.interval_diagnostics(
        None, (), all_covered, np.arange(10.0), cfg, budget()
    )
    assert partial_coverage[0]["empirical_coverage"] == pytest.approx(10 / 11)
    for residuals in ([], [np.nan], [-1]):
        with pytest.raises(ValueError, match="calibration"):
            analysis.interval_diagnostics(None, (), raw, np.array(residuals), cfg, budget())
    raw.loc[pd.Timestamp("2024-01-01"), "Demand"] = np.nan
    missing_rows, missing_summary = analysis.interval_diagnostics(
        None, (), raw, np.arange(10.0), cfg, budget()
    )
    assert missing_rows[0]["actual"] is None and missing_rows[0]["covered"] is None
    assert missing_summary[0]["origins"] == 11 and missing_summary[0]["planned_origins"] == 12
    absent = raw.drop(pd.Timestamp("2024-01-01"))
    _, absent_summary = analysis.interval_diagnostics(
        None, (), absent, np.arange(10.0), cfg, budget()
    )
    assert absent_summary[0]["missing_target_origins"] == 1
    for month in range(1, 13):
        raw.loc[pd.Timestamp(year=2024, month=month, day=1), "Demand"] = np.nan
    _, empty_summary = analysis.interval_diagnostics(None, (), raw, np.arange(10.0), cfg, budget())
    assert empty_summary[0]["origins"] == 0 and empty_summary[0]["empirical_coverage"] is None
    for invalid in (np.inf, -1):
        raw.loc[pd.Timestamp("2024-01-01"), "Demand"] = invalid
        with pytest.raises(ValueError, match="targets"):
            analysis.interval_diagnostics(None, (), raw, np.arange(10.0), cfg, budget())


def test_small_real_fits_reproduce_with_fixed_seed():
    config = protocol.load_config()
    config["parameters"]["n_estimators"] = 2
    t = np.arange(80.0)
    train = pd.DataFrame({"demand_lag_1h": t, "Demand": t + np.sin(t)})
    first, seconds = runner._fit(train, ("demand_lag_1h",), 42, config, budget())
    second, _ = runner._fit(train, ("demand_lag_1h",), 42, config, budget())
    np.testing.assert_array_equal(
        first.predict(train[["demand_lag_1h"]]), second.predict(train[["demand_lag_1h"]])
    )
    assert seconds > 0


@pytest.fixture
def fake_run(tmp_path, monkeypatch, raw):
    active = tmp_path / "models/electricity_xgb_prediction_model.pkl"
    active.parent.mkdir()
    active.write_bytes(b"packaged active model")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "load_hourly_data", lambda path: raw)
    monkeypatch.setattr(runner, "verify_provenance", lambda *args: None)
    monkeypatch.setattr(
        runner,
        "provenance",
        lambda path: {
            "git_revision": "abc",
            "git_dirty": True,
            "data_sha256": "data",
            "config_sha256": "config",
        },
    )

    def fake_fit(train, features, seed, config, limit):
        assert train.index.max() < pd.Timestamp("2024-01-01")
        limit.check(fit=True)
        return LagModel(), 0.001

    monkeypatch.setattr(runner, "_fit", fake_fit)
    monkeypatch.setattr(analysis, "recursive_predictions", lambda *args: np.full(168, 2000.0))
    config = write_config(tmp_path, protocol.load_config())
    return tmp_path, config, active


def test_full_protocol_repeat_outputs_and_active_artifact_preservation(fake_run):
    root, config, active = fake_run
    first_output = root / "first"
    first_output.mkdir()
    first = runner.run_experiment(config, first_output)
    second_output = root / "second"
    second_output.mkdir()
    second = runner.run_experiment(config, second_output)
    assert first["fits_completed"] == second["fits_completed"] == 28
    assert first["comparisons"] == second["comparisons"]
    assert first["historical_diagnostics"] == second["historical_diagnostics"]
    assert first["selected_variant"] == second["selected_variant"]
    assert first["run_id"] != second["run_id"]
    assert first["active_artifact_sha256_before"] == hashlib.sha256(active.read_bytes()).hexdigest()
    assert first["active_artifact_sha256_before"] == first["active_artifact_sha256_after"]
    assert active.read_bytes() == b"packaged active model"
    assert len(pd.read_csv(first_output / "runs.csv")) == 33
    assert first["historical_diagnostics"]["status"] == "reused_historical_2024_not_untouched_test"
    assert "Synthetic" in (first_output / "REPORT.md").read_text(encoding="utf-8")
    json.dumps(first, allow_nan=False)


def test_failed_active_artifact_integrity_prevents_success_report(fake_run, monkeypatch):
    root, config, active = fake_run
    original = runner.sha256
    calls = []

    def changed(path):
        calls.append(path)
        return original(path) if len(calls) == 1 else "unexpected change"

    monkeypatch.setattr(runner, "sha256", changed)
    output = root / "failed"
    output.mkdir()
    with pytest.raises(RuntimeError, match="Active model changed"):
        runner.run_experiment(config, output)
    assert not (output / "report.json").exists()
    assert active.read_bytes() == b"packaged active model"


def test_optional_tracking_dependency_failure_stops_before_any_fit(fake_run, monkeypatch):
    root, config, _ = fake_run

    def fail(*args):
        raise RuntimeError("missing optional SQLite dependency")

    def forbidden_fit(*args):
        pytest.fail("Optional tracking must be checked before any fit")

    monkeypatch.setattr(runner, "_local_tracking", fail)
    monkeypatch.setattr(runner, "_fit", forbidden_fit)
    with pytest.raises(RuntimeError, match="optional SQLite"):
        runner.run_experiment(config, root, tracking=True)


def test_cli_hard_deadline_and_worker_path_guard(tmp_path, monkeypatch):
    output = tmp_path / "experiments/reports/timeout"
    monkeypatch.setattr(runner, "prepare_output", lambda path: output)
    recorded = []

    def timeout(command, **kwargs):
        recorded.append((command, kwargs))
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(runner.subprocess, "run", timeout)
    assert runner.main(["--output", str(output), "--mlflow"]) == 124
    assert recorded[0][1]["timeout"] == 300
    assert "--mlflow" in recorded[0][0]
    assert recorded[0][1]["env"]["OMP_NUM_THREADS"] == "2"
    assert recorded[0][1]["env"]["MLFLOW_DISABLE_TELEMETRY"] == "true"
    with pytest.raises(ValueError, match="outside"):
        runner.main(["--worker", "--output", str(tmp_path / "models")])
    monkeypatch.setattr(
        runner.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0)
    )
    assert runner.main(["--output", str(output)]) == 0


def test_optional_tracking_writes_explicit_local_uri_and_portable_mapping(tmp_path, monkeypatch):
    recorded = {}

    class Active:
        info = SimpleNamespace(run_id="mlflow-id")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class FakeMlflow:
        def set_tracking_uri(self, uri):
            recorded["uri"] = uri

        def create_experiment(self, name, **kwargs):
            recorded.update(kwargs)
            return "experiment-id"

        def get_experiment_by_name(self, name):
            return None

        def set_experiment(self, **kwargs):
            pass

        def start_run(self, **kwargs):
            return Active()

        def log_params(self, params):
            pass

        def log_metrics(self, values):
            pass

        def log_metric(self, *args):
            pass

        def set_tags(self, tags):
            assert tags["synthetic"] == "true"

        def log_dict(self, value, name):
            assert "provenance" in value

    monkeypatch.setitem(sys.modules, "mlflow", FakeMlflow())
    report = {
        "config": protocol.load_config(),
        "provenance": {
            "git_revision": "abc",
            "git_dirty": True,
            "data_sha256": "data",
            "config_sha256": "config",
        },
    }
    row = {
        "run_id": "portable",
        "variant": "lags",
        "seed": 42,
        "fold": "2023",
        "train_rows": 10,
        "validation_rows": 5,
        "mae": 1.0,
        "rmse": 1.0,
        "wape": 1.0,
        "bias": 1.0,
        "fit_seconds": 0.1,
        "r2": 0.9,
    }
    tracked = runner._local_tracking(
        tmp_path, report, [row, {**row, "variant": "naive24", "r2": None}]
    )
    assert runner.os.environ["MLFLOW_DISABLE_TELEMETRY"] == "true"
    assert recorded["uri"].startswith("sqlite:///")
    assert str(tmp_path.as_posix()) in recorded["uri"]
    assert recorded["artifact_location"] == (tmp_path / "mlflow_artifacts").as_uri()
    assert tracked["runs"][0] == {"portable_run_id": "portable", "mlflow_run_id": "mlflow-id"}

    def missing(name):
        raise ImportError("optional package missing")

    monkeypatch.setattr(runner.importlib, "import_module", missing)
    with pytest.raises(RuntimeError, match="optional"):
        runner._local_tracking(tmp_path, report, [row])
