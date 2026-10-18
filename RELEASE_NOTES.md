# v0.2.0 release notes

This release adds controlled forecasting-service startup, artifact verification, reproducible research, and stronger release checks. The bundled dataset remains synthetic and recursive forecasts remain experimental.

## Application reliability

- An application factory and lifespan initialize each forecasting service explicitly. Importing API or evaluation modules does not load model or demand files.
- Readiness reports unavailable resources with HTTP 503; a separate liveness endpoint reports that the process is running.
- A trusted artifact manifest checks the packaged model checksum, feature order, and compatible XGBoost runtime before use.
- Input-specific diagnostics snapshots keep repeated dashboard requests from running full recursive backtests.
- Service settings capture the local timezone explicitly, so independent instances do not share mutable timezone configuration.
- Trusted model promotion updates the artifact manifest; publication failures restore the previous active model.

## Reproducible research

The bounded research workflow records configurations, chronological folds, seeds, data/code/lock hashes, sample counts, and metrics. It includes feature ablations, error slices, and empirical interval diagnostics, with optional local MLflow tracking. Research execution does not promote or overwrite the serving model.

See [the experiment instructions](docs/EXPERIMENTS.md), [the generated report](experiments/reports/bounded_synthetic_20261018_v2/REPORT.md), and [the model card](MODEL_CARD.md). The report records actual execution evidence and limitations; synthetic results do not establish operational performance.

## Verification

The release workflow enforces at least 90% branch-aware Python coverage, lint, formatting, type checks, dependency audits, Windows/Linux tests, and real browser scenarios against the containerized application. Test and coverage reports generate machine-readable evidence tied to the tested Git revision.

Follow [CONTRIBUTING.md](CONTRIBUTING.md) for development checks and [QUALITY_EVIDENCE.md](QUALITY_EVIDENCE.md) for the review checklist and CI evidence. Start the packaged application with `docker compose up --build` and open `http://localhost:8080`.

## Compatibility and limitations

The seven existing API endpoints retain their documented fields. New lifecycle handling requires test clients to enter the application lifespan. Operators promoting a model must review and commit its trusted manifest together with the artifact, then refresh diagnostics before release.

The original 2024 data has already informed evaluation/promotion decisions. Additional analyses of it are historical diagnostics, not a new independent final test. External data remains explicitly unverified until an operator establishes its origin and suitability. Repository eligibility and licensing offers remain subject to the evaluator's separate review.
