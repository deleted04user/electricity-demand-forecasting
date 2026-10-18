"""Keep scanner-visible package metadata aligned with the locked setup inputs."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[2]


def requirements(path: Path) -> set[Requirement]:
    """Resolve the project's local -r includes without installing anything."""
    declared = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.partition("#")[0].strip()
        if not line:
            continue
        if line.startswith("-r "):
            declared.update(requirements(path.parent / line.removeprefix("-r ").strip()))
        else:
            declared.add(Requirement(line))
    return declared


@pytest.mark.parametrize(
    ("extra", "filename"),
    [
        (None, "requirements-api.txt"),
        ("dev", "requirements-dev.txt"),
        ("research", "requirements-research.txt"),
        ("legacy", "requirements.txt"),
    ],
)
def test_pep621_dependency_sets_match_existing_installation_inputs(extra, filename):
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    core = [Requirement(value) for value in project["dependencies"]]
    optional = (
        [Requirement(value) for value in project["optional-dependencies"][extra]] if extra else []
    )
    for values in (core, optional):
        names = [canonicalize_name(value.name) for value in values]
        assert len(names) == len(set(names)), "Declare each dependency once per metadata group"
    assert set(core + optional) == requirements(ROOT / filename)
