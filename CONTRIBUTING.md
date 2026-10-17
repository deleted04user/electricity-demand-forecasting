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
python -m pytest --cov=backend --cov-report=term-missing
python -m pip_audit --strict --disable-pip -r requirements-api.lock.txt
```

Run `npm ci` followed by `npm run check` from `frontend/`. To validate the packaged application, run `docker compose up --build`, check `/api/health`, and open the dashboard. CI repeats automated quality checks; inspect its results on the commit you intend to review.

## Changes and tests

Keep changes focused and commits descriptive. Explain the actual defect or feature, the resulting behavior, and validation performed. For a bug fix, add a regression test that fails for the original behavior when practical. For API changes, test valid requests and relevant validation or failure paths. Test observable frontend behavior, including loading and errors, rather than internal implementation details.

Backend tests live in `backend/tests/`; frontend tests live alongside the source. Python test and coverage settings are in `pyproject.toml`. Use `python -m ruff format backend` to apply formatting. Keep API documentation, environment examples, and the changelog aligned with behavior changes.

## Dependencies

`requirements-api.txt`, `requirements-dev.txt`, and `requirements.txt` are maintainer inputs. Commit their corresponding `.lock.txt` files when updating dependencies. Consumers install from the locks with pip and `--require-hashes`. Generate locks with uv for Python 3.12:

```bash
uv pip compile requirements-api.txt --python-version 3.12 --universal --generate-hashes -o requirements-api.lock.txt
uv pip compile requirements-dev.txt --python-version 3.12 --universal --generate-hashes -c requirements-api.lock.txt -o requirements-dev.lock.txt
uv pip compile requirements.txt --python-version 3.12 --universal --generate-hashes -c requirements-api.lock.txt -o requirements.lock.txt
```

Run quality and vulnerability checks after regenerating. The optional notebook/Streamlit dependencies in `requirements.lock.txt` are separate from the API environment.

Use `npm ci` with the committed frontend lock. Include both `frontend/package.json` and `frontend/package-lock.json` for dependency changes. Dependabot proposes updates through pull requests; review and validate them before merging.

## Data and model integrity

Keep synthetic data clearly labeled. Do not introduce credentials, private electricity records, or third-party assets without the necessary rights. Do not claim that synthetic-data scores measure production forecasting accuracy. The provenance checks identify the known bundled sample and recognized copies; other files remain `caller_supplied_unverified` with `synthetic_data: null`. Never infer verified real-world provenance from a successful schema check or a different file path.

Feature engineering must use only information available at the forecast origin. Keep training and serving features consistent, preserve chronological evaluation, and compare against naive baselines. The current training procedure uses fixed pre-2024 and 2024 periods; changing that contract requires corresponding tests and documentation. Do not repeatedly tune against a final holdout and then report it as independent evidence.

Retraining changes artifacts and requires a local file supplied explicitly with `--data`. The operator must verify its origin, suitability, and usage rights; the software does not certify external inputs as real data. The bundled sample and recognized copies are refused. Review the retained candidate, evaluation report, lineage, and any archived model before accepting a promotion. Load only trusted serialized model artifacts.
