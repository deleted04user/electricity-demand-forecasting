"""Start the real Compose stack and record readiness and one resource sample."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen


def verify_health(payload: Any) -> None:
    """An HTTP 200 alone must not certify a ready, bundled demo."""
    if (
        not isinstance(payload, dict)
        or payload.get("status") != "ok"
        or payload.get("model_ready") is not True
        or payload.get("data_ready") is not True
        or payload.get("synthetic_data") is not True
        or payload.get("data_provenance") != "bundled_synthetic"
        or type(payload.get("observations")) is not int
        or payload["observations"] <= 0
    ):
        raise ValueError("Expected a ready API serving the bundled synthetic data")


def read_health(base_url: str) -> dict[str, Any]:
    with urlopen(base_url + "/api/health", timeout=10) as response:
        payload = json.load(response)
    verify_health(payload)
    return payload


def resource_samples(output: str, containers: list[str]) -> list[dict[str, Any]]:
    samples = [json.loads(line) for line in output.splitlines() if line]
    if (
        len(samples) != len(containers)
        or any(not isinstance(sample, dict) for sample in samples)
        or {sample.get("ID") for sample in samples} != set(containers)
        or any(not sample.get("CPUPerc") or not sample.get("MemUsage") for sample in samples)
    ):
        raise ValueError("Expected CPU/memory samples for both running containers")
    for sample in samples:
        try:
            cpu = float(sample["CPUPerc"].removesuffix("%"))
            memory = sample["MemUsage"].split("/")
            if (
                not math.isfinite(cpu)
                or cpu < 0
                or len(memory) != 2
                or not all(
                    re.fullmatch(r"\s*\d+(?:\.\d+)?(?:[kKMGTPE]i?B|B)\s*", part) for part in memory
                )
            ):
                raise ValueError
        except (AttributeError, TypeError, ValueError):
            raise ValueError("CPU/memory sample is unavailable") from None
    return samples


def record(api_url: str, frontend_url: str) -> dict[str, Any]:
    started = time.perf_counter()
    subprocess.run(
        [
            "docker",
            "compose",
            "up",
            "--no-build",
            "--pull",
            "never",
            "-d",
            "--wait",
            "--wait-timeout",
            "180",
        ],
        check=True,
    )
    ready_seconds = time.perf_counter() - started
    direct = read_health(api_url)
    proxied = read_health(frontend_url)
    if direct != proxied:
        raise ValueError("Direct and proxied API readiness disagree")
    with urlopen(frontend_url + "/", timeout=10) as response:
        if response.status != 200 or b'<div id="root">' not in response.read():
            raise ValueError("The dashboard HTML did not load")
    containers = subprocess.check_output(["docker", "compose", "ps", "-q"], text=True).split()
    if len(containers) != 2:
        raise ValueError("Expected both backend and frontend containers")
    stats = subprocess.check_output(
        ["docker", "stats", "--no-trunc", "--no-stream", "--format", "{{json .}}", *containers],
        text=True,
    )
    samples = resource_samples(stats, containers)
    return {
        "schema_version": 1,
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "tracked_changes": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=no"], text=True
            ).strip()
        ),
        "generated_at": datetime.now(UTC).isoformat(),
        "compose_ready_seconds": round(ready_seconds, 3),
        "health": direct,
        "dashboard_http_status": 200,
        "direct_and_proxy_health_match": True,
        "container_resource_sample": samples,
        "container_images": {
            container: subprocess.check_output(
                ["docker", "inspect", "--format", "{{.Image}}", container], text=True
            ).strip()
            for container in containers
        },
        "host": {"platform": platform.platform(), "logical_cpus": os.cpu_count()},
        "measurement_scope": (
            "Compose up through health-check readiness; image build/download excluded. "
            "Docker CPU/memory is one idle sample after startup, not peak load or a capacity guarantee. "
            "git_sha/tracked_changes describe the checkout; image IDs identify the tested images."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--frontend-url", default="http://127.0.0.1:8080")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = record(args.api_url.rstrip("/"), args.frontend_url.rstrip("/"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Compose ready in {report['compose_ready_seconds']} seconds; evidence: {args.output}")


if __name__ == "__main__":
    main()
