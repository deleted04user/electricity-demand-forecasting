# Running the React + FastAPI demo

The demo runs locally without credentials or network data feeds. Its bundled workbook is synthetic and its recursive forecasts are experimental. Use Python 3.12 and Node.js 24.15+ (24.x LTS) with npm, or Docker with Compose.

## Docker Compose

From the repository root with Docker's engine running:

```bash
docker compose up --build
```

Open the [dashboard](http://localhost:8080), [API docs](http://localhost:8000/docs), and [health endpoint](http://localhost:8000/api/health). Nginx forwards the frontend's `/api` requests to FastAPI. Stop the stack with `docker compose down`. To use different host ports, set `FRONTEND_PORT` and `API_PORT` in your shell or root `.env` before starting Compose.

### Startup and resources

Allow two CPU cores and 2 GiB of available RAM as a starting development budget
for this small bundled model; this is a planning allowance, not a measured minimum
or a throughput guarantee. Initial image downloads/builds depend on the network
and build cache. After images are built, CI allows 180 seconds for Compose health
checks to become ready; a mismatched diagnostic snapshot may take longer than
the normal prepared-snapshot startup.

Run the same measured smoke check as CI after `docker compose build`:

```bash
python scripts/container_evidence.py --output tmp/container-evidence.json
```

It starts both containers, requires ready model/data plus the bundled synthetic
provenance from the direct and proxied API, loads the dashboard HTML, and records
time through Compose readiness and one Docker CPU/memory sample. Each Quality
workflow's `browser-report` artifact includes `container-evidence.json`, tied to
its actual commit and runner. Startup excludes image builds; the idle sample
does not measure peak memory or capacity under load. Use that artifact when
comparing machines rather than treating the timeout as an expected startup time.

One [measured CI run](https://github.com/deleted04user/electricity-demand-forecasting/actions/runs/39250696182)
at revision `313270f` reached readiness in **16.998 seconds** on a four-logical-CPU
Linux runner. Its idle sample was **163.3 MiB / 0.17% CPU** for the backend and
**5.422 MiB / 0.00% CPU** for nginx/frontend. The [raw measurement](docs/benchmarks/container-ci-20261019.json)
retains image IDs and timing scope. This is one observation with prebuilt images,
not an expected result on every machine. Readiness still reports the bundled
data's known gaps in `data_quality`; HTTP 200 does not certify complete data.

## Windows PowerShell

Open a terminal at the cloned repository root. These commands use the virtual environment's interpreter directly, so PowerShell script-activation policies do not need changing:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-api.lock.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --env-file .env --reload --port 8000
```

If `py -3.12` is unavailable, use a Python 3.12 installation's `python` command. Virtual environments are specific to their machine and interpreter; create a fresh one after cloning. If `.venv` already belongs to a different interpreter, create `.venv-local` and substitute that name in the commands.

In a second terminal at the same repository root:

```powershell
cd frontend
npm ci
npm run dev
```

Open [localhost:5173](http://localhost:5173). Vite proxies `/api` requests to `http://127.0.0.1:8000`. The backend's interactive API contract is at [localhost:8000/docs](http://localhost:8000/docs).

## macOS / Linux

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-api.lock.txt
cp .env.example .env
python -m uvicorn backend.main:app --env-file .env --reload --port 8000
```

Use the same frontend commands from a second terminal. Keep both servers running while using the dashboard.

## Configure local inputs

Uvicorn loads the root `.env` only when passed `--env-file .env`. Restart the backend after changing its configuration. Leave optional file paths unset to run the packaged demo. See [the data contract](README.md#local-data-configuration) before supplying another source.

Frontend configuration is separate: copy `frontend/.env.example` to `frontend/.env` only when you need an API URL override. `VITE_API_BASE_URL` is public browser configuration, read by Vite when starting or building. It must never contain secrets. For a different API origin, also set the backend's `CORS_ORIGINS` to the actual dashboard origin.

For Docker, paths in backend configuration must exist inside the container. Mount external input files and pass the corresponding container paths through Compose's `environment` or `env_file`; a host path alone does not make a file available inside a container.

## Make a forecast request

With the backend running, this PowerShell example uses the correct next forecast hour from API metadata:

```powershell
$metadata = Invoke-RestMethod http://localhost:8000/api/meta
$requestBody = @{ start = $metadata.future_start; horizon = 24 } | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/api/forecast/future -Method Post -ContentType 'application/json' -Body $requestBody
```

`start` must exactly equal `future_start` without a timezone suffix. `horizon` is an integer from 1 to 168. To supply weather, include both `temperature` and `humidity` arrays with one finite value per requested hour; humidity must be 0–100. Otherwise, the API uses a configured local weather file or labels its historical weather proxy. Predicted demand feeds subsequent lag features; historical one-step metrics do not measure accuracy across the full recursive horizon.

## Verification and optional tools

Install `requirements-dev.lock.txt` for the Python quality tools and tests, then follow [CONTRIBUTING.md](CONTRIBUTING.md). In `frontend/`, `npm run check` runs lint, tests, and the production build. Build output is `frontend/dist/`; `npm run preview` serves it for local inspection.

With Compose running, install Chromium from `frontend/` using `npx playwright install --with-deps --only-shell chromium`, then run `npm run test:e2e`. The browser scenario exercises real historical and recursive forecasts and verifies recovery after a controlled failure.

For reproducible research, install `requirements-research.lock.txt` and follow [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md). Runs have explicit fit/time/thread limits and unique report directories. They never overwrite the served model.

For the optional legacy UI, install `requirements.lock.txt` with `python -m pip install --require-hashes -r requirements.lock.txt` in a separate environment, then run `python -m streamlit run dashboard.py`. That broader environment is separate from the API runtime. Retraining is an intentional artifact-changing operation; follow [the training contract](README.md#evaluation-and-retraining) and provide verified data with `--data`.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Docker cannot connect to its engine | Start Docker Desktop or your Docker engine before running Compose. |
| Port 8000, 5173, or 8080 is in use | Stop the conflicting process or choose another port; update the Vite proxy/API override when changing the backend port. |
| Dashboard reports an API/network error | Open `/api/health` on port 8000, confirm the backend is running, and check `VITE_API_BASE_URL` and CORS when using separate origins. |
| Backend reports HTTP 503 | Check `/api/live` for process liveness and the structured startup logs for the resource failure. Confirm the workbook, trusted model, and `models/artifact-manifest.json` are present and compatible; correct configuration and restart. |
| Trusted manifest rejects a newly trained model | Promote through the guarded training command and review/commit the model and manifest together. Avoid replacing a serialized artifact from an unknown source. |
| Diagnostics need refreshing after a reviewed model/data change | Run `python -m backend.evaluate --diagnostics` and review the new input identity and results. A mismatched snapshot is recomputed during startup. |
| Forecast returns a validation error | Use `/api/meta`'s exact `future_start`, an integer horizon within 1–168, and complete weather arrays when supplied. |
| API returns HTTP 413 | Keep request bodies within `MAX_REQUEST_BODY_BYTES` (default 64 KiB); weather arrays accept at most 168 numeric values each. The setting is captured at backend startup. |
| Dashboard says the backend request timed out | Requests have a 30-second deadline through response-body parsing. Check backend readiness/logs and network access, then retry; the future-forecast button becomes available again. |
| Data-quality status requires attention | Inspect reported gaps, duplicates, and missing values before using the predictions. |
