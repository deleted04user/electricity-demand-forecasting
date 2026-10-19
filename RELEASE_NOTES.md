# v0.3.1 release notes

This patch bounds malformed or stalled requests while preserving valid forecasts.

- The API uses Starlette's built-in request-body limiter: 64 KiB by default,
  counting actual streamed bytes as well as declared length. `MAX_REQUEST_BODY_BYTES`
  accepts 1 KiB–1 MiB at startup. Expected HTTP 413 responses retain request IDs and
  allowed CORS headers without generating unexpected-error events.
- Weather arrays accept finite JSON numbers, reject boolean/string coercion and
  contain at most 168 entries. Existing horizon, humidity and next-hour rules remain.
- Browser requests have a 30-second deadline through response-body parsing.
  Deadlines are cleared after completion and isolated between concurrent requests;
  the forecast button becomes available again after a timeout.
- Regression coverage includes streamed/misleading lengths, boundary values,
  per-request/app isolation, privacy/correlation, stalled response headers/bodies
  and actual UI recovery. A real container API test rejects bad requests and then
  makes a successful forecast. Local checks passed 225 backend tests with 95.53%
  branch-aware coverage, plus 30 frontend tests, lint, types and production build.

Starlette's required minimum is now explicit; its locked version was already
1.8.0. All resolved package versions and scientific prediction code remain
unchanged. Two [fresh frozen studies](experiments/reports/bounded_synthetic_20261019_v5/REPORT.md)
executed 28 fits and 33 local MLflow comparisons each, in 188.891 and 132.032 seconds.
The [independent audit](experiments/reports/bounded_synthetic_20261019_v5/reproduction_check.json)
found zero numeric differences against each other and historical v4, verified
current native metadata/lock identities and retained the active model hash.
Earlier reports remain immutable. See [reproduction instructions](docs/EXPERIMENTS.md).

The [Quality workflow](https://github.com/deleted04user/electricity-demand-forecasting/actions/workflows/quality.yml)
and [Security workflow](https://github.com/deleted04user/electricity-demand-forecasting/actions/workflows/security.yml)
provide revision-specific release evidence. [v0.3.0](https://github.com/deleted04user/electricity-demand-forecasting/releases/tag/v0.3.0)
introduced native locking, optional private error reporting, security analysis
and measured container evidence; those capabilities are retained.

The bundled data is synthetic and reused 2024 diagnostics remain historical.
The latest external assessment displays 80 (B); this patch needs a new assessment
after the daily cooldown. Tests do not establish an external score or offer.
