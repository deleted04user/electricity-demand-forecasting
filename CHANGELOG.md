# Changelog

This log records substantive changes from the repository's development history.

## v0.3.0 — 2026-10-19

- Adopt a native `uv.lock` with five verified pip hash exports, preserving existing package versions; exercise locked installs on Linux/Windows and audit the optional reporting environment too.
- Add default-off, application-owned Sentry error reporting with a private event schema, bounded shutdown, request-ID correlation, and real SDK transport regression tests.
- Test rendered demand/correlation values, observed diagnostic metric/baseline/horizon rows, and HTTP/network/JSON failures in the React analytics pages.
- Verify ready model/data and bundled provenance through the direct/proxied API; record actual container startup time, image identities and idle CPU/memory samples with failure guards.
- Add CodeQL analysis for Python, JavaScript and Actions, a security policy and formal threat model; clarify local deployment and legacy UI boundaries.
- Include native metadata/lock identities in frozen research provenance; retain earlier studies as historical evidence.

## v0.2.1 — 2026-10-18

- Declare standard Python package metadata and dependency groups, including the required Pydantic 2 minimum, while retaining the tested locked package versions.
- Document every environment setting with working defaults and clarify which processes load them.
- Use the conventional `docker-compose.yml` filename for tool discovery; retain the verified two-service configuration.

## v0.2.0 — 2026-10-18

- Introduced a managed application lifespan, independent forecast-service instances, frozen settings, and a separate liveness endpoint with controlled readiness failures.
- Verified trusted model checksums and feature/runtime metadata before loading; paired successful promotion with manifest publication and rollback on failure.
- Prepared diagnostic snapshots identified by their inputs, source code, and runtime versions; kept full backtests outside ordinary request paths.
- Added finite typed response schemas and honest null handling for undefined statistics, plus explicit per-instance timezone configuration.
- Added a bounded, reproducible synthetic research workflow with chronological feature ablations, seed repeats, error slices, interval diagnostics, portable provenance, and optional local MLflow tracking.
- Raised the backend coverage gate to 90%, added real container-backed Chromium tests and generated revision-specific quality evidence, and updated supported CI runtimes.
- Added a model card, experiment instructions, release notes, quality-evidence map, and regression coverage for the new boundaries.

## 2026-10-17 — Reproducible setup and quality checks

- Added separate locked Python API and development environments with Python 3.12 as the supported runtime.
- Added backend lint, formatting, type, and coverage checks, with Linux and Windows CI coverage and dependency vulnerability checks.
- Added Docker packaging and a Compose stack serving the dashboard through nginx with an `/api` reverse proxy.
- Updated frontend API routing to support same-origin development and deployment, with an optional explicit API origin.
- Added backend and frontend regression coverage for data validation and API request behavior.
- Rejected ambiguous or invalid hourly inputs and invalid weather values.
- Unified data-provenance reporting across the API, evaluation manifest, and training reports; recognized bundled-data copies remain synthetic and are refused for training, while external inputs remain explicitly unverified.
- Added request IDs and structured API logs with request bodies and query strings excluded.
- Replaced starter frontend documentation, documented environment configuration and reproducible verification, and added contributor guidance.

The bundled demonstration data remains synthetic. Forecasting scope and metric limitations are documented in the [README](README.md).
