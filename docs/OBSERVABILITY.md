# Optional error reporting

The default API writes JSON logs to stderr. Every response includes a generated
`X-Request-ID`, including unexpected HTTP 500 responses; use it to find the
corresponding `request_failed` and `request_completed` records. Expected HTTP
validation errors and resource-unavailable responses retain their normal status.

For external aggregation, install the locked optional dependency from the
repository root:

```bash
uv sync --locked --extra observability
```

The pip equivalent in a Python 3.12 environment is:

```bash
python -m pip install --require-hashes -r requirements-observability.lock.txt
```

Set `SENTRY_DSN` to your destination and optionally set `SENTRY_ENVIRONMENT`
(default `production`), then start Uvicorn with `--env-file .env`. Keep real
configuration outside Git. An empty DSN disables reporting and does not import
the SDK or create a transport. The base Docker image uses only the API lock and
has reporting disabled; a deployment enabling it must install the observability
lock in its image and supply the settings at runtime. A root `.env` is Compose
variable substitution, not automatic backend environment injection.

Reporting belongs to each application's lifespan. It uses a separate Sentry
client with automatic integrations disabled, captures unexpected request
exceptions once, and closes with a bounded flush during shutdown. It does not
replace readiness or the local logs. An unavailable reporter must not turn an
otherwise usable forecasting service into a failed startup or response.

Events allow only the error type, generated request ID, HTTP method, route
template, and backend module/function/line frames. Exception messages, local
variables, source contents, absolute paths, request bodies, query strings,
headers, cookies, user context and breadcrumbs are excluded. Tracing, profiling,
automatic logs and metrics are disabled. Local stderr still contains exception
details: apply suitable log access and retention policies there.

Tests use fake and in-memory transports without contacting Sentry. They cover
disabled reporting, configured capture, privacy, independent applications,
startup/shutdown and reporter failure. See [the threat model](THREAT_MODEL.md)
for the deployment boundary and [Sentry's Python SDK](https://docs.sentry.io/platforms/python/)
for destination administration. Creating a Sentry account is optional and is not
part of running the bundled project.
