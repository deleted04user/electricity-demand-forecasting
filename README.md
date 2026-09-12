# Electricity demand forecasting

This is a **synthetic-data local demonstration**, not an operational forecast. React + FastAPI is the primary application; `dashboard.py` is the optional legacy Streamlit dashboard. See [local setup](RUNNING_THE_REACT_DASHBOARD.md).

## Verified model result

The active XGBoost model was promoted only after it beat the previous artifact on the same 8,666 valid rows in the untouched 2024 holdout.

| Model | MAE (MW) | RMSE (MW) | R² | WAPE | Bias (MW) |
|---|---:|---:|---:|---:|---:|
| 24-hour naive | 178.25 | 224.53 | 0.7860 | 6.09% | -0.99 |
| 168-hour naive | 144.33 | 181.99 | 0.8594 | 4.93% | -1.15 |
| Previous XGBoost | 112.95 | 141.32 | 0.9152 | 3.86% | -59.99 |
| Active improved XGBoost | **103.72** | **130.22** | **0.9280** | **3.55%** | **-28.58** |

Bias is mean(prediction − actual), so negative values indicate underforecasting.

## Methodology

`backend/features.py` is the shared causal feature implementation. Weather is forward-filled only; leading missing values remain null. Demand lags use 1, 2, 3, 6, 12, 24, 48, 72, 168 and 336 prior hours. Rolling mean/std features use demand shifted by one hour with 6-, 24- and 168-hour windows. Calendar inputs include raw and cyclical hour/day-of-week signals, weekend and Moroccan public holidays. Temperature squared is included. Ramadan was not added because no reliable existing local dependency supplied that indicator.

`backend/modeling.py` owns metrics, chronological splits, three expanding rolling-origin validation folds, two naive baselines, and guarded training. One bounded search evaluated eight manually defined configurations. Selection used mean 2023 validation WAPE with RMSE as tie-breaker. The selected regularized depth-5 configuration used 2023 for early-stopping round selection (1,328 trees), was refit on history through 2023, and was evaluated once on 2024. The previous artifact was backed up before promotion; feature order, parameters, periods, metrics, baselines, checksums and selection evidence are recorded in `models/metadata.json` and the versioned evaluation report.

## Forecast scope

Reported accuracy is historical one-step-ahead/short-horizon performance using observed prior demand and weather. The 1–168 hour future endpoint is explicitly experimental: predictions feed later lag/rolling features and errors can accumulate. Its historical weather proxy is not a weather forecast.

## Operational data contract and configuration

The bundled workbook remains **synthetic demonstration data**. The API never downloads data or calls a weather provider. To use verified local operational data, set `ELECTRICITY_DATA_PATH` to a `.csv`, `.xlsx`, or `.xls` file before starting the API. It must contain exactly usable `Timestamp`, `Demand`, `Temperature`, and `Humidity` columns (additional columns are allowed). `Timestamp` must be hourly, sorted or sortable, unambiguous in the configured local timezone (documented default: `Africa/Casablanca`), and must not contain duplicates. Demand is numeric; humidity is percentage; temperature is numeric.

The API reports duplicates, missing hourly timestamps, missing demand/weather, 3×IQR outlier counts, coverage and model/data compatibility at `/api/health` and `/api/meta`. It never silently repairs source data. Feature generation forward-fills only prior weather; it never backfills/interpolates weather. Demand targets are never imputed; a forecast requires enough causal history for the active feature schema.

For real future weather without secrets, set `WEATHER_FORECAST_PATH` to a local CSV/XLSX with `Timestamp`, `Temperature`, and `Humidity`, covering every requested future hour. Otherwise the API clearly labels its deterministic historical month/hour proxy fallback. Callers may instead provide both weather arrays in the future-forecast request. No provider is enabled until credentials/configuration are explicitly added by an operator.

Optional non-public events must be supplied via `VERIFIED_EVENTS_PATH`, a local CSV/XLSX with `Date` and `Event`. Invalid or absent records are not invented; no extra events are assumed. These dates augment the existing Morocco public-holiday calendar.

Intervals are 90% empirical held-out absolute-residual estimates; recursive horizons use a conservative sqrt-horizon scaling. They are estimates, not guarantees. Model performance now distinguishes observed-lag one-step scores from sampled recursive 1h, 6h, 24h, 72h, and 168h diagnostics using the historical-weather proxy.

## Safe retraining

Only retrain with verified real local data: `python -m backend.modeling --train --data C:\path\to\verified_hourly.csv`. The command refuses the bundled synthetic workbook, keeps every candidate under `models/candidates`, uses chronological 2023 rolling validation, evaluates the untouched 2024 holdout once, and promotes only when WAPE **or** RMSE strictly improves on common held-out rows. Keep an unchanged 2024-equivalent heldout segment in the supplied data; otherwise do not run promotion. `python -m backend.evaluate --manifest` refreshes active-model lineage and fixed recursive diagnostics.
