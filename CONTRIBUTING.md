# Contributing

Use Python 3.12 and Node.js 24.15+ (24.x LTS). Follow the [running guide](RUNNING_THE_REACT_DASHBOARD.md) to start the demo. Install development dependencies from the repository root in a fresh virtual environment:

```bash
python -m pip install --require-hashes -r requirements-dev.lock.txt
```

Run these checks before submitting a change:

```bash
python -m ruff check backend
python -m ruff format --check backend
python -m mypy backend
python -m pytest --cov=backend --cov-fail-under=90 --cov-report=term-missing
python -m pip_audit --strict --disable-pip -r requirements-api.lock.txt
```

Run `npm ci` followed by `npm run check` from `frontend/`. To validate the packaged application, run `docker compose up --build`, check `/api/health`, and open the dashboard. CI repeats automated quality checks; inspect its results on the commit you intend to review.

Run real browser integration tests against the stack from `frontend/`:

```bash
npx playwright install --with-deps --only-shell chromium
npm run test:e2e
```

The default browser-test origin is `http://127.0.0.1:8080`; `E2E_BASE_URL` can select another live deployment. Successful forecast requests use the actual backend. Only the deliberate failure scenario intercepts a response, then retries against the live service.

## Changes and tests

Keep changes focused and commits descriptive. Explain the actual defect or feature, the resulting behavior, and validation performed. For a bug fix, add a regression test that fails for the original behavior when practical. For API changes, test valid requests and relevant validation or failure paths. Test observable frontend behavior, including loading and errors, rather than internal implementation details.

Backend tests live in `backend/tests/`; frontend tests live alongside the source. Python test and coverage settings are in `pyproject.toml`. Use `python -m ruff format backend` to apply formatting. Keep API documentation, environment examples, and the changelog aligned with behavior changes.

Settings, artifact, request/response, service, application, and evaluation boundaries have strict mypy enforcement. Preserve at least 90% branch-aware backend coverage and test failure behavior. Use `with TestClient(create_app(...)) as client` so tests exercise startup and shutdown. Avoid shared global runtime state and implicit data/model loading on import.

## Dependencies

`pyproject.toml` declares the compatible dependency groups; semantic tests keep
the `requirements*.txt` declarations aligned. The native `uv.lock` resolves all
groups for Python 3.12. Five pip-compatible hash exports support API, development,
research, legacy and optional observability installations. Use uv 0.13.0 to
maintain them:

```bash
uv lock
python scripts/lock_dependencies.py --write
uv lock --check
python scripts/lock_dependencies.py --check
```

Use `uv lock --upgrade-package NAME` for an intentional package update. Commit
`pyproject.toml`, requirement declarations, `uv.lock` and affected exports together,
then run quality and vulnerability checks. Never change a pin or hash directly
in an export. `uv sync --locked --extra dev` installs the development environment;
`uv run --locked --extra dev python -m pytest` uses that exact environment. Pip
consumers and Docker continue using `--require-hashes`. The notebook/Streamlit
dependencies in `requirements.lock.txt` remain separate from the API environment.

The research lock includes development tools and optional local experiment tracking. Follow [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) before running experiments. Keep research artifacts separate from production promotion, declare the protocol before comparing results, and retain the code/config/data provenance attached to each report.

Use `npm ci` with the committed frontend lock. Include both `frontend/package.json` and `frontend/package-lock.json` for dependency changes. Dependabot proposes updates through pull requests; review and validate them before merging.

Dependabot targets the native `uv` ecosystem. For a Python update PR, align any
changed direct requirement declarations and regenerate the pip exports before
merging; the export/metadata guards intentionally fail until those files agree.

## Data and model integrity

Keep synthetic data clearly labeled. Do not introduce credentials, private electricity records, or third-party assets without the necessary rights. Do not claim that synthetic-data scores measure production forecasting accuracy. The provenance checks identify the known bundled sample and recognized copies; other files remain `caller_supplied_unverified` with `synthetic_data: null`. Never infer verified real-world provenance from a successful schema check or a different file path.

Feature engineering must use only information available at the forecast origin. Keep training and serving features consistent, preserve chronological evaluation, and compare against naive baselines. The current training procedure uses fixed pre-2024 and 2024 periods; changing that contract requires corresponding tests and documentation. Do not repeatedly tune against a final holdout and then report it as independent evidence.

Retraining changes artifacts and requires a local file supplied explicitly with `--data`. The operator must verify its origin, suitability, and usage rights; the software does not certify external inputs as real data. The bundled sample and recognized copies are refused. Review the retained candidate, evaluation report, lineage, and any archived model before accepting a promotion. Load only trusted serialized model artifacts.
