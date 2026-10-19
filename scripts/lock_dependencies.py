"""Check or regenerate pip-compatible hash exports from the native uv lock."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = {
    "requirements-api.lock.txt": None,
    "requirements-dev.lock.txt": "dev",
    "requirements-research.lock.txt": "research",
    "requirements.lock.txt": "legacy",
    "requirements-observability.lock.txt": "observability",
}
HEADER = (
    "# Generated from uv.lock; do not edit package pins or hashes by hand.\n"
    "# Regenerate: python scripts/lock_dependencies.py --write\n"
)


def export(uv: str, extra: str | None) -> str:
    command = [
        uv,
        "export",
        "--locked",
        "--no-emit-project",
        "--no-header",
        "--no-annotate",
        "--no-default-groups",
        "--python",
        sys.executable,
        "--no-python-downloads",
    ]
    if extra is not None:
        command.extend(["--extra", extra])
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)
    return HEADER + result.stdout.replace("\r\n", "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Fail on stale exports (the default)")
    mode.add_argument(
        "--write", action="store_true", help="Write exports after an explicit uv lock"
    )
    args = parser.parse_args()
    uv = shutil.which("uv")
    if uv is None:
        parser.error("Install uv 0.13.0 before checking or regenerating dependencies")
    stale = []
    try:
        for filename, extra in EXPORTS.items():
            expected = export(uv, extra)
            path = ROOT / filename
            if args.write:
                path.write_text(expected, encoding="utf-8", newline="\n")
            elif not path.is_file() or path.read_bytes() != expected.encode("utf-8"):
                stale.append(filename)
    except subprocess.CalledProcessError as error:
        print(error.stderr, file=sys.stderr)
        return error.returncode
    if stale:
        print("Stale lock exports: " + ", ".join(stale), file=sys.stderr)
        print("Run python scripts/lock_dependencies.py --write after uv lock", file=sys.stderr)
        return 1
    print(
        f"{'Wrote' if args.write else 'Verified'} {len(EXPORTS)} hash-locked exports from uv.lock"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
