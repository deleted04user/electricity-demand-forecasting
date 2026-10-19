# Python packaging and locked environments

`pyproject.toml` is the standard project declaration: name, version, Python 3.12,
MIT license, runtime requirements and optional `dev`, `research`, `legacy` and
`observability` extras. Semantic metadata tests compare every dependency group
with its pip-compatible `requirements*.txt` declaration.

## Reproduce an environment

The native `uv.lock` is the single resolved dependency graph. Use uv 0.13.0:

```bash
uv sync --locked                         # API only
uv sync --locked --extra dev             # tests, types, lint and audits
uv sync --locked --extra research        # dev tools plus local MLflow/SQLite
uv sync --locked --extra observability   # API plus optional Sentry SDK
uv sync --locked --extra legacy          # optional notebooks / Streamlit
```

Select one environment appropriate to the task. By default `uv sync` removes
packages absent from the selected groups; use separate checkout environments
when working on different groups concurrently. `uv run --locked --extra dev
python -m pytest` keeps development commands on the locked interpreter/packages.

The five `requirements*.lock.txt` files are generated hash exports of that same
graph. Pip installations and Docker remain supported with no uv runtime:

```bash
python -m pip install --require-hashes -r requirements-api.lock.txt
```

Use the dev/research/observability/legacy export for the corresponding environment.
Compatible ranges in project metadata alone do not reproduce the trusted model's
runtime. CI exercises native locked development installs on Linux and Windows,
pip hash installs for dependency audits, and the pip-installed API Docker image.

Starlette is declared directly with a minimum of 1.8 because the API uses its
built-in streamed-body limiter. This makes that feature requirement explicit
rather than depending on an older unconstrained transitive installation. The
locked Starlette version was already 1.8.0; no package upgrade was needed.

## Maintain the graph and exports

Update compatible requirements in `pyproject.toml` and their requirement inputs
together. Then run:

```bash
uv lock
python scripts/lock_dependencies.py --write
uv lock --check
python scripts/lock_dependencies.py --check
```

Use `uv lock --upgrade-package NAME` for a deliberate version upgrade. The export
checker compares exact bytes and fails on stale pins, hashes or group selection;
CI runs it before installing the native environment. Audit all five exports after
an update. Never edit generated pins/hashes by hand.

The migration to the native graph retained all previously selected versions in
the four established environments. The optional reporting SDK is the sole new
package in dev/research; the base API environment still excludes it. Exports
contain hashes relevant to the supported Python version rather than every
artifact for unrelated Python versions. Native resolution and install checks
cover the supported platforms.

## Distribution scope and research provenance

Setuptools builds only the `backend` package, excluding its tests. Data/model
artifacts, frontend assets, configs and research reports remain checkout
resources: run serving/research commands from the repository root. The legacy
Streamlit script is not part of the API wheel or image and imports the shared
backend feature and metric functions.

If using pip, optionally register a hash-installed checkout with `python -m pip
install --no-deps -e .`. To inspect a wheel without installing runtime packages,
use `uv build --wheel --out-dir tmp/package-build` with Python 3.12 available.

Research provenance includes both `pyproject.toml` and `uv.lock`, as well as the
exported locks, configuration, scientific source and data/model identities. New
reports record the new dependency bytes; existing reports remain immutable
historical evidence. Changing a lock does not justify rewriting old provenance
or claiming a scientific improvement.
