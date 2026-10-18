"""Build release evidence from actual test/coverage reports for this checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def generate(coverage_path: Path, junit_path: Path, minimum_coverage: float = 90) -> dict[str, Any]:
    if not math.isfinite(minimum_coverage) or not 0 <= minimum_coverage <= 100:
        raise ValueError("Minimum coverage must be a finite percentage between 0 and 100")
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    percent = float(coverage["totals"]["percent_covered"])
    if not math.isfinite(percent) or not minimum_coverage <= percent <= 100:
        raise ValueError(f"Coverage {percent} is below the required {minimum_coverage}%")
    if coverage["meta"].get("branch_coverage") is not True:
        raise ValueError("Release evidence requires branch coverage")
    suites = list(ET.parse(junit_path).getroot().iter("testsuite"))
    tests = sum(int(suite.get("tests", "0")) for suite in suites)
    failed = sum(
        int(suite.get("failures", "0")) + int(suite.get("errors", "0")) for suite in suites
    )
    skipped = sum(int(suite.get("skipped", "0")) for suite in suites)
    if tests <= skipped or failed:
        raise ValueError("Release evidence requires executed tests with zero failures and errors")
    locks = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(ROOT.glob("requirements*.lock.txt"))
    }
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "git_sha": git("rev-parse", "HEAD"),
        "tracked_changes": bool(git("status", "--porcelain", "--untracked-files=no")),
        "backend": {
            "tests": tests,
            "failures_and_errors": failed,
            "skipped": skipped,
            "coverage_percent": percent,
            "branch_coverage": True,
            "minimum_coverage": minimum_coverage,
        },
        "dependency_locks_sha256": locks,
        "model_sha256": hashlib.sha256(
            (ROOT / "models/electricity_xgb_prediction_model.pkl").read_bytes()
        ).hexdigest(),
        "scope": "Backend test evidence only; frontend, security and containers have separate CI jobs.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-coverage", type=float, default=90)
    args = parser.parse_args()
    payload = generate(args.coverage, args.junit, args.minimum_coverage)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Wrote backend quality evidence for {payload['git_sha']} to {args.output}")


if __name__ == "__main__":
    main()
