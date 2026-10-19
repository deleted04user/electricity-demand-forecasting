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
| Analysis | `experiments/reports/bounded_synthetic_20261019_v5/`, `scripts/audit_reproduction.py` | Portable run/segment/interval tables, repeat study, independent stdlib audit, and `MODEL_CARD.md` with limitations |
| Dependencies | Native `uv.lock`, five generated `requirements*.lock.txt` exports and frontend `package-lock.json` | Locked native installs on Linux/Windows, exact export drift checks, hash-checked pip/Docker installs, all-group vulnerability audits and native-uv Dependabot updates |
| Packaged application | Root/frontend Dockerfiles, `docker-compose.yml`, nginx proxy | Container build, readiness, dashboard/API smoke requests, real Chromium forecast/error/recovery tests |
| Deployment measurements | `scripts/container_evidence.py` | JSON readiness/provenance checks through direct/proxy paths; prebuilt-image startup time, image IDs, dirty status and validated idle Docker resource samples |
| Private error aggregation | `backend/error_reporting.py`, `docs/OBSERVABILITY.md` | Default-off lifecycle, real SDK in-memory capture, request-ID correlation, privacy/independent-app/failure regressions |
| Security | `SECURITY.md`, `docs/THREAT_MODEL.md`, `.github/workflows/security.yml` | CodeQL Python/JavaScript/Actions, dependency audits, repository secret scanning and push protection, private vulnerability reporting |
| Onboarding | `README.md`, `RUNNING_THE_REACT_DASHBOARD.md`, environment examples, `CONTRIBUTING.md` | Explicit fresh-clone commands; release validation uses the supported Python/Node runtimes |

## Machine-readable evidence

Backend CI generates evidence from completed reports rather than hardcoded test counts:

```bash
python -m pytest --cov=backend --cov-fail-under=90 --cov-report=xml --cov-report=json --junitxml=test-results/backend.xml
python scripts/quality_evidence.py --coverage coverage.json --junit test-results/backend.xml --output quality-evidence.json
```

The evidence records the Git SHA, whether tracked files changed, executed/skipped test counts, coverage percentage, branch-coverage status, dependency-lock hashes, and active-model hash. The builder rejects failing/empty test reports, non-branch coverage, and invalid/below-threshold percentages. Evidence-builder regression tests exercise these rejection cases.

Download the Linux/Windows coverage artifacts and browser-report artifact from the matching workflow run. The frontend, dependency-audit, and container/browser jobs provide their own validation logs. The backend JSON deliberately identifies its scope rather than implying that it proves other jobs passed.

The `browser-report` artifact also contains `container-evidence.json`, with actual
startup/resource measurements and endpoint checks. Builds/downloads are excluded
from that startup timer; Docker statistics are one idle sample, not peak resource
requirements. Image IDs identify what ran, while Git fields identify the checkout.
The separate [Security analysis workflow](https://github.com/deleted04user/electricity-demand-forecasting/actions/workflows/security.yml)
publishes CodeQL results; inspect open code-scanning alerts as well as job status.

The [v0.3.0 implementation run](https://github.com/deleted04user/electricity-demand-forecasting/actions/runs/39250696182)
passed all five Quality jobs: Linux and Windows each ran **203 tests**, with
**95.62% branch-aware coverage**, zero failures and zero skips. The frontend
passed 25 component tests, lint and its production build, and the live container
browser scenarios passed. [All three CodeQL analyses](https://github.com/deleted04user/electricity-demand-forecasting/actions/runs/39250696057)
passed, with no open findings when reviewed. CI evidence identifies the exact
revision and platform; later release artifacts retain their own tested SHA.

v0.3.1 adds HTTP body limits, strict bounded weather arrays and browser deadlines.
Its local Windows run passed **225 backend tests at 95.53% branch-aware coverage**;
frontend lint, **30 tests** and the production build passed. Additional live API
integration checks reject oversized/ambiguous inputs and verify a subsequent
valid forecast. Release artifacts record the final CI results separately.

## Experiment reproduction

Follow [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) and the checked-in protocol. Use a new directory for a repeated run; existing results are not overwritten. Compare metrics using the protocol's declared tolerance, while retaining the new run's own environment, Git state, and content hashes. Do not replace an old report's provenance after execution.

The study is explicitly synthetic research. The served artifact is protected from the research runner, and the reused 2024 diagnostic period is not presented as a newly independent final test. An operator must establish the origin and suitability of external data.

## External assessment

The next supplied assessment, on 19 October 2026, displays **80 (B)** with a
non-binding $120 estimate. It recognizes the completed environment example and
Compose setup but still fails to discover the four already tracked Python hash
locks and incorrectly describes shared legacy imports as duplicate algorithms.
The current release addresses genuine testing, reporting, security and dependency
workflow gaps; its score requires a fresh assessment after the daily cooldown.

A fresh public-copy DataFactor assessment on 18 October 2026 returned **79.5 overall (B)**, an increase of 16.8 points from the previously supplied 62.7. The website displayed the rounded value **80**; the emailed report supplied the precise score. It recognized the tested service, bounded experiments, MLflow, strict checks and browser integration. It still missed the existing Compose file and Python lock inputs in some structural statistics; standard package metadata, complete environment documentation and the conventional Compose filename address the useful follow-up findings.

[Release v0.2.0](https://github.com/deleted04user/electricity-demand-forecasting/releases/tag/v0.2.0) and [its final five-job Quality run](https://github.com/deleted04user/electricity-demand-forecasting/actions/runs/39100290251) preserve that engineering baseline. The external report does not expose an analyzed SHA, so match its scan time and evidence against the submitted revision before attributing a later score. Scores and licensing estimates are separate from executable CI evidence.

Readiness for installation, tests, and review is verifiable here. The evaluator's minimum source volume, task capacity, numerical weights, and offer decision are separate requirements. The repository history should be assessed as it actually exists, including real focused changes and tests; release tags and documentation do not substitute for sustained maintenance.
