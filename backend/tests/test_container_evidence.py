"""Deployment evidence must distinguish HTTP success from model readiness."""

import json

import pytest
from scripts import container_evidence
from scripts.container_evidence import resource_samples, verify_health


@pytest.mark.parametrize(
    "change",
    [
        {"status": "unavailable"},
        {"model_ready": False},
        {"data_ready": False},
        {"observations": 0},
        {"observations": True},
        {"synthetic_data": None},
        {"data_provenance": "caller_supplied_unverified"},
    ],
)
def test_unready_or_unverified_data_cannot_be_published_as_demo_evidence(change):
    payload = {
        "status": "ok",
        "model_ready": True,
        "data_ready": True,
        "observations": 24,
        "synthetic_data": True,
        "data_provenance": "bundled_synthetic",
    }
    verify_health(payload)
    with pytest.raises(ValueError, match="ready API"):
        verify_health(payload | change)


@pytest.mark.parametrize("identifiers", [[], ["a"], ["a", "a"], ["a", "unknown"]])
def test_incomplete_or_unrelated_resource_samples_cannot_be_published(identifiers):
    output = "\n".join(
        json.dumps({"ID": identifier, "CPUPerc": "0.00%", "MemUsage": "100MiB / 2GiB"})
        for identifier in identifiers
    )
    with pytest.raises(ValueError, match="both running containers"):
        resource_samples(output, ["a", "b"])


@pytest.mark.parametrize(
    "change",
    [
        {"CPUPerc": "--"},
        {"CPUPerc": "NaN%"},
        {"MemUsage": "-- / --"},
        {"MemUsage": " / "},
        {"MemUsage": "unknown / 2GiB"},
    ],
)
def test_available_resources_are_recorded_and_unavailable_stats_are_rejected(change):
    samples = [
        {"ID": identifier, "CPUPerc": "0.00%", "MemUsage": "100MiB / 2GiB"}
        for identifier in ["a", "b"]
    ]
    output = "\n".join(json.dumps(sample) for sample in samples)
    assert resource_samples(output, ["a", "b"]) == samples
    samples[0].update(change)
    with pytest.raises(ValueError, match="unavailable"):
        resource_samples("\n".join(json.dumps(sample) for sample in samples), ["a", "b"])


def test_direct_and_proxied_readiness_must_match_before_sampling_resources(monkeypatch):
    commands = []
    monkeypatch.setattr(
        container_evidence.subprocess, "run", lambda args, **kw: commands.append(args)
    )
    payloads = iter([{"observations": 24}, {"observations": 48}])
    monkeypatch.setattr(container_evidence, "read_health", lambda url: next(payloads))
    with pytest.raises(ValueError, match="readiness disagree"):
        container_evidence.record("http://api", "http://frontend")
    assert "--no-build" in commands[0]
    assert commands[0][commands[0].index("--pull") + 1] == "never"
