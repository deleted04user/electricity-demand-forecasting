# v0.3.0 release notes

This release strengthens dependency reproducibility, diagnostics testing and
operational evidence around the existing forecasting service.

- A native `uv.lock` resolves the project and all optional groups. Five generated
  pip hash exports remain available for API/Docker, development, research,
  observability and legacy environments. CI checks exact export consistency and
  actually installs the native locked environment on Linux and Windows. Existing
  package versions are retained; Sentry is an optional new dependency.
- Opt-in Sentry reporting belongs to each application lifespan. It aggregates
  unexpected errors with generated request IDs and a strict operational-field
  allowlist. Automatic request/PII capture, tracing and profiling are disabled;
  reporter failures preserve API behavior. Real SDK in-memory tests cover these
  contracts without contacting an external service.
- Focused analytics tests verify rendered demand/correlation values, actual
  baseline/horizon diagnostics and HTTP/network/invalid-JSON failure states.
- Container checks require ready model/data and bundled provenance through the
  direct and proxied API. Revision-specific evidence records startup timing,
  image IDs and validated idle CPU/memory samples. The running guide links a real
  measured CI sample and states its limits.
- CodeQL analyzes Python, JavaScript and Actions. The security policy and threat
  model document trusted model serialization, inputs, research isolation, local
  deployment boundaries and responsibilities when exposing the service.
- Two fresh frozen research studies use native-lock/project provenance. Their
  independent stdlib audit compares JSON/CSV counts and metrics, verifies local
  tracking records when present and preserves old reports unchanged.

The two [research runs](experiments/reports/bounded_synthetic_20261019_v4/REPORT.md)
completed 28 fits and 33 local MLflow comparisons each, in 67.140 and 47.281
seconds. Compared numeric results match exactly, including the historical v3
study; the model artifact is unchanged. The [audit proof](experiments/reports/bounded_synthetic_20261019_v4/reproduction_check.json)
and [reproduction commands](docs/EXPERIMENTS.md) retain their scope and input hashes.
The workbook is synthetic and reused 2024 diagnostics remain historical.

The [Quality workflow](https://github.com/deleted04user/electricity-demand-forecasting/actions/workflows/quality.yml)
gates lint, formatting, strict service types, 90% branch-aware coverage,
Linux/Windows tests, dependency audits and live Docker/Chromium scenarios. The
[Security workflow](https://github.com/deleted04user/electricity-demand-forecasting/actions/workflows/security.yml)
provides separate CodeQL results. Release evidence files identify the exact
revision and actual counts; consult [QUALITY_EVIDENCE.md](QUALITY_EVIDENCE.md),
[packaging](docs/PACKAGING.md) and [optional reporting](docs/OBSERVABILITY.md).

The latest external assessment displays 80 (B). This release needs a new scan
after the evaluator's daily cooldown; implementation checks do not establish a
new score or a licensing offer. [CHANGELOG.md](CHANGELOG.md) records preceding
releases.
