# Python project metadata

`pyproject.toml` exposes the project name, version, supported Python runtime,
license, runtime dependencies and optional `dev`, `research` and `legacy`
dependency groups through standard PEP 621 metadata. Package scanners and Python
installation tools can inspect these without interpreting CI or Docker scripts.

The `requirements*.txt` inputs remain the dependency declaration source used to
generate the existing hashed locks. The PEP 621 dependency arrays mirror those
inputs for standard tooling. `backend/tests/test_project_metadata.py` resolves
the local requirement includes and checks exact semantic equality for every
group, preventing either declaration from drifting unnoticed. A change to a
direct dependency must update its requirement input and corresponding metadata
group before regenerating only the affected lock files.

The runtime dependency set matches `requirements-api.txt`. The `dev` extra adds
the developer tooling from `requirements-dev.txt`; `research` includes those
tools plus the local MLflow/SQLite dependencies from `requirements-research.txt`.
The `legacy` extra adds the optional notebook and Streamlit dependencies from
`requirements.txt`. Existing hash-locked setup instructions remain the
reproducible installation path.

Setuptools builds only the `backend` Python package and excludes tests and
unrelated repository directories. The wheel intentionally contains Python
modules and metadata; model/data artifacts, frontend assets, configuration and
research reports remain repository resources. Run the application and research
commands from the documented checkout. If editable package registration is
useful, first install the matching hash-locked environment, then register the
checkout without resolving dependencies again:

```powershell
python -m pip install --require-hashes -r requirements-dev.lock.txt
python -m pip install --no-deps -e .
```

Use the API or research lock instead when that environment is intended. The
unpinned project metadata declares compatible dependency ranges; it does not
reproduce the serving environment. In particular, the trusted model manifest
checks its required XGBoost runtime version, so broad package metadata cannot
replace the checked-in lock for running the packaged model.

To inspect/build metadata without installing project dependencies:

```powershell
uv build --wheel --out-dir tmp/package-build
python -m pip install --dry-run --ignore-installed --no-deps --report tmp/package-metadata.json .
```

The package supports Python 3.12, which is the runtime exercised by the repository
CI and lock files. Adding standard metadata also makes the existing Pydantic 2
runtime requirement explicit in `requirements-api.txt`: the API uses Pydantic 2
validators and must not accept a Pydantic 1 installation. All four locks were
regenerated under their existing version constraints, with every resolved
package version, platform marker and artifact hash preserved. Only declaration
provenance changed; no installed runtime upgrade was required.

The updated lock bytes have new provenance hashes. Fresh version-three
experiment runs record those hashes, while earlier reports remain immutable
historical evidence. The scientific model configuration and source are unchanged.
