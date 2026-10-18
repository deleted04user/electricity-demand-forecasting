# Quality evidence for repository review

Use the commit SHA of the [Quality workflow](https://github.com/deleted04user/electricity-demand-forecasting/actions/workflows/quality.yml) you are reviewing. A passing run verifies that revision; it does not establish an external score or a licensing offer.

## Review map

| Area | Implementation | Verification |
| --- | --- | --- |
| Startup and ownership | `backend/settings.py`, `backend/service.py`, `backend/main.py` | Isolated service instances, import-time I/O guards, lifespan initialization/shutdown, and controlled readiness failures in `backend/tests/test_runtime.py` and API tests |
| Artifact integrity | `backend/artifacts.py`, `models/artifact-manifest.json` | Checksum checked before trusted deserialization, metadata/schema/runtime compatibility tests; promotion rollback tests |
| Prepared diagnostics | `models/diagnostics.json` and input-specific service identity | Changed model/data/code/events/timezone cannot reuse a prior snapshot; schema rejects non-finite cached model results |
| Data and forecasting contracts | `backend/ingestion.py`, `backend/features.py`, typed API schemas | Hourly/timezone/finite-value validation, causal feature checks, historical/future API tests, independent timezone tests |
| Code checks | `pyproject.toml`, `.github/workflows/quality.yml` | Ruff lint/format, mypy including strict service boundaries, Linux and Windows tests |
| Coverage | Branch coverage with a 90% floor | CI coverage JSON/XML, JUnit results, and generated `quality-evidence.json` in each backend artifact |
| Reproducible research | `configs/experiments.json`, `backend/experiments*.py` | Fixed chronological folds, bounded fits/time/threads, seeds and identity hashes, optional local MLflow tracking, protocol tests |
| Analysis | `experiments/reports/bounded_synthetic_20261018_v2/` | Portable run/segment/interval tables, executed report, and `MODEL_CARD.md` with limitations |
| Dependencies | Four `requirements*.lock.txt` files and frontend `package-lock.json` | Hash-checked Python installs, Python/npm vulnerability audits, and Dependabot configuration |
| Packaged application | Root/frontend Dockerfiles, `compose.yaml`, nginx proxy | Container build, readiness, dashboard/API smoke requests, real Chromium forecast/error/recovery tests |
| Onboarding | `README.md`, `RUNNING_THE_REACT_DASHBOARD.md`, environment examples, `CONTRIBUTING.md` | Explicit fresh-clone commands; release validation uses the supported Python/Node runtimes |

## Machine-readable evidence

Backend CI generates evidence from completed reports rather than hardcoded test counts:

```bash
python -m pytest --cov=backend --cov-fail-under=90 --cov-report=xml --cov-report=json --junitxml=test-results/backend.xml
python scripts/quality_evidence.py --coverage coverage.json --junit test-results/backend.xml --output quality-evidence.json
```

The evidence records the Git SHA, whether tracked files changed, executed/skipped test counts, coverage percentage, branch-coverage status, dependency-lock hashes, and active-model hash. The builder rejects failing/empty test reports, non-branch coverage, and invalid/below-threshold percentages. Evidence-builder regression tests exercise these rejection cases.

Download the Linux/Windows coverage artifacts and browser-report artifact from the matching workflow run. The frontend, dependency-audit, and container/browser jobs provide their own validation logs. The backend JSON deliberately identifies its scope rather than implying that it proves other jobs passed.

## Experiment reproduction

Follow [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) and the checked-in protocol. Use a new directory for a repeated run; existing results are not overwritten. Compare metrics using the protocol's declared tolerance, while retaining the new run's own environment, Git state, and content hashes. Do not replace an old report's provenance after execution.

The study is explicitly synthetic research. The served artifact is protected from the research runner, and the reused 2024 diagnostic period is not presented as a newly independent final test. An operator must establish the origin and suitability of external data.

## External assessment

The previously supplied score report repeats missing-lock/Docker/CI claims from an earlier revision. A new assessment should identify its analyzed commit and scan time. Match those against the published files and completed workflow before comparing category scores.

Readiness for installation, tests, and review is verifiable here. The evaluator's minimum source volume, task capacity, numerical weights, and offer decision are separate requirements. The repository history should be assessed as it actually exists, including real focused changes and tests; release tags and documentation do not substitute for sustained maintenance.
