# Local demo completion

React + FastAPI is the primary local application; the historical forecast comparison and legacy Streamlit dashboard remain available. Data is synthetic and this is not a production forecasting system.

- Paths resolve from source files; API URL and CORS origins are configurable.
- Shared causal features preserve hourly spacing, forward-fill weather/history, retain missing targets, and add strictly historical multi-scale lags/rolling statistics plus cyclical calendar and temperature-squared signals.
- Three rolling-origin folds select configuration on 2023 history; early stopping selects tree count before refitting through 2023. The final held-out test remains 2024.
- Promoted-model test metrics: MAE 103.72 MW, RMSE 130.22 MW, R² 0.9280, WAPE 3.55%, Bias -28.58 MW. The prior model scored MAE 112.95 MW, RMSE 141.32 MW, R² 0.9152, WAPE 3.86%, Bias -59.99 MW on the identical rows.
- Performance API/UI compare 24-hour and 168-hour naive baselines on the same test rows.
- Future API/UI recursively forecast 1–168 hours after packaged history with supplied weather (API) or clearly labelled historical proxies; this mode is experimental and accumulates error.
- `python -m backend.evaluate` evaluates two historical recursive origins without retraining; `--manifest` regenerates lineage and checksums.
- Backend tests cover readiness, overview/meta, historical/future validation, causal missing-value handling and recursive lag feedback. Frontend tests cover the new controls and baseline presentation.

See `RUNNING_THE_REACT_DASHBOARD.md` for clean-machine setup. Existing `.venv` is machine-specific and untouched. The prior active artifact is versioned under `models/archive`, the promoted candidate remains under `models/candidates`, and the misspelled root model is inactive. Notebook outputs remain historical. No external services or deployment were added.
