"""Release evidence must fail closed for failed tests or invalid coverage reports."""

import json

import pytest
from scripts import quality_evidence


@pytest.mark.parametrize(
    "percentage,branches,tests,failures,skipped",
    [
        (89, True, 2, 0, 0),
        (float("nan"), True, 2, 0, 0),
        (101, True, 2, 0, 0),
        (95, False, 2, 0, 0),
        (95, True, 2, 1, 0),
        (95, True, 0, 0, 0),
        (95, True, 2, 0, 2),
    ],
)
def test_invalid_test_results_cannot_be_published_as_release_evidence(
    tmp_path, percentage, branches, tests, failures, skipped
):
    coverage = tmp_path / "coverage.json"
    coverage.write_text(
        json.dumps(
            {"totals": {"percent_covered": percentage}, "meta": {"branch_coverage": branches}}
        )
    )
    junit = tmp_path / "junit.xml"
    junit.write_text(
        f'<testsuites><testsuite tests="{tests}" failures="{failures}" '
        f'errors="0" skipped="{skipped}" /></testsuites>'
    )
    with pytest.raises(ValueError):
        quality_evidence.generate(coverage, junit)


def test_passing_evidence_uses_report_counts_and_identifies_the_tested_revision(
    tmp_path, monkeypatch
):
    (tmp_path / "models").mkdir()
    (tmp_path / "models/electricity_xgb_prediction_model.pkl").write_bytes(b"test artifact")
    (tmp_path / "requirements-api.lock.txt").write_text("example==1\n")
    monkeypatch.setattr(quality_evidence, "ROOT", tmp_path)
    monkeypatch.setattr(
        quality_evidence, "git", lambda *args: "a" * 40 if args[0] == "rev-parse" else ""
    )
    coverage = tmp_path / "coverage.json"
    coverage.write_text(
        json.dumps({"totals": {"percent_covered": 95.5}, "meta": {"branch_coverage": True}})
    )
    junit = tmp_path / "junit.xml"
    junit.write_text(
        '<testsuites><testsuite tests="12" failures="0" errors="0" skipped="1" /></testsuites>'
    )
    report = quality_evidence.generate(coverage, junit)
    assert report["git_sha"] == "a" * 40 and report["tracked_changes"] is False
    assert report["backend"]["tests"] == 12 and report["backend"]["skipped"] == 1
    assert report["backend"]["coverage_percent"] == 95.5
    assert len(report["dependency_locks_sha256"]["requirements-api.lock.txt"]) == 64
