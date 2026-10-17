# Changelog

This log records substantive changes from the repository's development history.

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
