# v0.2.1 release notes

This patch makes the verified forecasting application easier to install and inspect with standard tools. It builds on v0.2.0's managed service lifecycle, trusted model validation, prepared diagnostics, bounded research and container/browser checks.

- Standard Python project metadata declares runtime dependencies and optional development, research and legacy groups. Semantic consistency tests keep those declarations aligned with the requirement inputs.
- The API explicitly requires Pydantic 2, matching the validation features it uses. Regenerated hash locks retain every previously tested package version and artifact hash.
- The complete environment example has working bundled-data defaults, empty optional weather/event overrides, research privacy settings, browser-test settings and Compose ports. Documentation explains which process loads each value.
- `docker-compose.yml` supplies the existing API and nginx/frontend services under the conventional discovery filename. Start them together with `docker compose up --build` and open `http://localhost:8080`.

The model artifact and scientific configuration remain unchanged. Fresh [research evidence](experiments/reports/bounded_synthetic_20261018_v3/REPORT.md) records the new lock-file bytes; earlier measured reports retain their original provenance. Read [the model card](MODEL_CARD.md), [experiment instructions](docs/EXPERIMENTS.md) and [packaging scope](docs/PACKAGING.md) when reproducing the work.

The [Quality workflow](https://github.com/deleted04user/electricity-demand-forecasting/actions/workflows/quality.yml) enforces a 90% branch-aware coverage floor, lint, formatting, types, Linux/Windows tests, dependency audits and Chromium scenarios against the Docker stack. Its artifacts identify the tested revision. See [QUALITY_EVIDENCE.md](QUALITY_EVIDENCE.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

The bundled data remains synthetic, and reused 2024 diagnostics are not an independent final test. Research metrics do not establish operational accuracy or a licensing offer. [CHANGELOG.md](CHANGELOG.md) records the preceding runtime and research changes.
