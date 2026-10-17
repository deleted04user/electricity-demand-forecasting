# Electricity Demand Forecasting

[![Quality](https://github.com/deleted04user/electricity-demand-forecasting/actions/workflows/quality.yml/badge.svg)](https://github.com/deleted04user/electricity-demand-forecasting/actions/workflows/quality.yml)

Hourly demand analysis and XGBoost forecasting, served by FastAPI with a React dashboard. The repository includes causal feature engineering, chronological evaluation, naive baselines, data-quality reporting, and an experimental 1–168 hour recursive forecast.

**The bundled workbook is synthetic demonstration data.** Its metrics demonstrate the implementation; they do not establish forecasting accuracy for a real electricity system. Retrain and validate on verified real data before operational or commercial forecasting use.

![Dashboard overview](figures/capture_vue_ensemble.png)

## Run with Docker

Install Docker with Compose, start its engine, and run from the repository root:

```bash
docker compose up --build
```

Open the dashboard at [localhost:8080](http://localhost:8080), the API documentation at [localhost:8000/docs](http://localhost:8000/docs), or the health endpoint at [localhost:8000/api/health](http://localhost:8000/api/health). The frontend forwards `/api` requests to the backend. No credentials or external data services are required for the bundled demo.

Stop with `docker compose down`. `API_PORT` and `FRONTEND_PORT` optionally override the default published ports. See [the local running guide](RUNNING_THE_REACT_DASHBOARD.md) for configuration and troubleshooting.

## Run from source

Use **Python 3.12** and **Node.js 24.15+ (24.x LTS)** with npm. Runtime and development Python dependencies have separate lock files; `requirements.lock.txt` adds optional notebooks and the legacy Streamlit dashboard.

```bash
git clone https://github.com/deleted04user/electricity-demand-forecasting.git
cd electricity-demand-forecasting
python -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-api.lock.txt
cp .env.example .env
python -m uvicorn backend.main:app --env-file .env --reload --port 8000
```

On Windows PowerShell, activate with `.\.venv\Scripts\Activate.ps1` and copy the environment example with `Copy-Item .env.example .env`. [The running guide](RUNNING_THE_REACT_DASHBOARD.md) includes complete PowerShell commands without requiring activation.

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open [localhost:5173](http://localhost:5173). Vite proxies `/api` to the backend at `127.0.0.1:8000`; an optional `VITE_API_BASE_URL` overrides that behavior. See [frontend/README.md](frontend/README.md).

## Verify a checkout

From the root, with the Python environment active:

```bash
python -m pip install --require-hashes -r requirements-dev.lock.txt
python -m ruff check backend
python -m ruff format --check backend
python -m mypy backend
python -m pytest --cov=backend --cov-report=term-missing
python -m pip_audit --strict --disable-pip -r requirements-api.lock.txt
```

Then run `npm ci` and `npm run check` from `frontend/` for lint, component tests, and a production build. CI runs the backend checks on Linux and Windows and checks the frontend and containers. Coverage requirements are defined in [pyproject.toml](pyproject.toml); current results are available in the [Quality workflow](https://github.com/deleted04user/electricity-demand-forecasting/actions/workflows/quality.yml). See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow.

## Architecture and methodology

```mermaid
flowchart TD
    A[Hourly demand and weather] --> B[Validation and quality report]
    B --> C[Causal feature engineering]
    C --> D[XGBoost model]
    D --> E[FastAPI service]
    E --> F[React dashboard]
    D --> G[Evaluation and lineage metadata]
```

[backend/features.py](backend/features.py) is shared by training and serving. It builds demand lags from 1 to 336 hours, rolling mean and standard deviation after shifting demand by one hour, calendar and Moroccan public-holiday signals, cyclical time encodings, and weather features. Weather is forward-filled only; missing demand targets are excluded from evaluation.

[backend/modeling.py](backend/modeling.py) uses chronological boundaries, three expanding 2023 validation folds, and a bounded eight-configuration search. Candidate selection minimizes mean validation WAPE, with RMSE as the tie-breaker. The selected configuration is then evaluated on common usable 2024 rows against the active model and 24-hour/168-hour naive baselines. Candidates and promotion reports retain evaluation evidence.

### Bundled model evaluation

These values are recorded in [models/metadata.json](models/metadata.json), using 8,666 usable rows in the synthetic 2024 holdout. Historical metrics use observed prior demand and weather.

| Model | MAE (MW) | RMSE (MW) | R² | WAPE | Bias (MW) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 24-hour naive | 178.25 | 224.53 | 0.7860 | 6.09% | -0.99 |
| 168-hour naive | 144.33 | 181.99 | 0.8594 | 4.93% | -1.15 |
| Active XGBoost | 103.72 | 130.22 | 0.9280 | 3.55% | -28.58 |

Bias is `mean(prediction - actual)`. The future endpoint feeds earlier predictions into later lag features, so its error can grow with horizon. Without supplied future weather, it explicitly labels its historical month/hour proxy. Empirical 90% prediction intervals are estimates, not guarantees.

## API

Interactive request and response schemas are available at `/docs` and `/openapi.json`.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Service, model, and data-quality status |
| `GET /api/meta` | Historical date range, next forecast start, and configuration |
| `GET /api/overview` | Summary statistics and daily demand series |
| `GET /api/demand-analysis` | Hourly/monthly patterns and correlations |
| `GET /api/model-performance` | Metrics, baselines, feature importance, and diagnostics |
| `GET /api/forecast?date=2024-12-31&hour=12` | Historical actual-versus-predicted comparison |
| `POST /api/forecast/future` | Experimental recursive future forecast |

For future forecasts, use `future_start` from `/api/meta` as the timezone-naive `start`, and an integer `horizon` from 1 to 168. Optional `temperature` and `humidity` arrays must both contain exactly `horizon` finite numbers; humidity must be within 0–100. Explicit arrays take precedence over a configured weather file. See [the running guide](RUNNING_THE_REACT_DASHBOARD.md) for an executable request.

Responses include an `X-Request-ID` for correlating requests with structured JSON logs on stderr. Request logs record method, path, status, and duration; they omit query strings and request bodies. Unexpected failures include error details for diagnosis.

## Local data configuration

Copy [.env.example](.env.example) to `.env` and pass `--env-file .env` to Uvicorn. Environment values are read when the backend starts; restart it after changes.

| Variable | Purpose / default |
| --- | --- |
| `ELECTRICITY_DATA_PATH` | Local demand CSV/XLSX; defaults to the bundled workbook |
| `ELECTRICITY_TIMEZONE` | Local clock timezone for aware demand timestamps; `Africa/Casablanca` |
| `WEATHER_FORECAST_PATH` | Optional local future-weather CSV/XLSX |
| `VERIFIED_EVENTS_PATH` | Optional local CSV/XLSX containing `Date` and `Event` |
| `CORS_ORIGINS` | Comma-separated allowed browser origins; local Vite origins by default |

Demand data requires `Timestamp`, `Demand`, `Temperature`, and `Humidity`. Use unique timestamps aligned to whole hours and numeric measurements; use either naive local timestamps or consistently timezone-aware timestamps. Invalid timestamps, non-finite measurements, negative demand, and humidity outside 0–100 are rejected. Explicit missing values and hourly gaps remain visible in the quality report. The weather file requires `Timestamp`, `Temperature`, and `Humidity` covering every requested future hour, with aware timestamps converted to the configured local clock. CSV, XLSX, and legacy XLS readers are included in the locked API environment.

The quality report flags duplicate timestamps, gaps, missing values, outliers, and compatibility with the model's required history. Review the report before forecasting. Supplying another file does not retrain the bundled model or validate it for that source.

The API metadata, health response, and evaluation manifest identify the bundled sample and recognized copies as `synthetic_data: true` with `data_provenance: "bundled_synthetic"`. Other local files are reported as `synthetic_data: null` and `data_provenance: "caller_supplied_unverified"`. Schema validation does not establish a file's origin: the operator must verify that data is real, suitable, and authorized for use.

## Evaluation and retraining

```bash
python -m backend.evaluate
python -m backend.evaluate --manifest
python -m backend.modeling --train --data /path/to/verified_hourly.csv
```

The first command runs fixed recursive backtests. `--manifest` refreshes `models/metadata.json` for the configured model and data. Training refuses the bundled workbook and recognized copies. Verify the origin and suitability of any replacement before supplying it with `--data`; accepting its schema does not certify it as real data. The current training procedure requires data spanning the hard-coded pre-2024 training/validation periods and 2024 test period; it preserves candidates and archives the active artifact before a promotion. Promotion requires improved WAPE or RMSE on common holdout rows. Preserve an independent final evaluation period when developing against new data; repeated selection on the same holdout makes that holdout unsuitable as unbiased final evidence.

Only load model artifacts from trusted sources: serialized Python model files can execute code when loaded.

## Repository guide

| Path | Contents |
| --- | --- |
| `backend/` | API, ingestion, features, modeling, evaluation, and Python tests |
| `frontend/` | React/Vite dashboard and component tests |
| `data/` | Synthetic demonstration workbook |
| `models/` | Active artifact, candidates, archive, and lineage metadata |
| `.github/` | Quality workflow and dependency-update configuration |
| `figures/`, `scripts/` | Report screenshots and capture automation |
| `dashboard.py` | Optional legacy Streamlit dashboard |

See [CHANGELOG.md](CHANGELOG.md) for documented changes. Original project software uses the [MIT License](LICENSE); third-party report and data assets retain their respective rights.
