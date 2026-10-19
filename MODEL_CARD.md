# Electricity demand model card

## Intended use and provenance

This repository demonstrates hourly electricity-demand forecasting and its supporting API/dashboard. The bundled `data/electricity_demand_2025.xlsx` workbook is **synthetic**. Its metrics describe this generated dataset and do not establish accuracy, reliability or economic value on a real Moroccan electricity grid.

The intended use is local experimentation, reproducible research and software demonstration. Grid dispatch, capacity procurement and other consequential operational decisions require independent real data, validation and an operational review. Caller-supplied datasets are explicitly unverified; replacing the file does not establish ownership or origin.

## Active packaged model

The active artifact is `models/electricity_xgb_prediction_model.pkl`, an XGBoost regressor packaged with its ordered feature schema and training/split metadata. The model currently uses calendar/cyclical features, holiday/weekend indicators, temperature/humidity, demand lags from 1 to 336 hours and past-only rolling statistics over 6, 24 and 168 hours. Features must match the package contract exactly.

The packaged model was trained through 2023 and compared on historical 2024 data. Earlier promotion used 2024 comparisons, so **2024 is no longer an untouched holdout**. `models/metadata.json` records the artifact hash, parameters, provenance and diagnostic results; those exported values should be read together with their timestamps and scope. The historical packaged model's contemporaneous weather features also differ from the strictly lagged weather availability used by the new research benchmark.

The API's observed-row diagnostics measure sequential one-step forecasting, where prior demand can be observed before the next prediction. Recursive forecasts use predicted values as future demand inputs and historical weather proxies when a weather scenario is not supplied. Their errors can grow rapidly; they should not inherit one-step accuracy claims. User-supplied future weather is a scenario, not verified observed weather.

## Separate research model and evidence

The bounded command documented in [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) compares naive demand baselines and five fixed feature groups on three predeclared expanding 2023 folds. All comparisons share timestamps and causal input availability. The lags/full models repeat seeds 42/43/44. Selection uses only seed-42 2023 fold WAPE, with RMSE as tie-breaker. The selected research estimator is refit through 2023 solely for reused historical 2024 diagnostics.

The runner uses the same synthetic workbook under an explicit research-only exemption; it never serializes or promotes an estimator. It preserves the production-training guard against synthetic data and checks the active artifact hash before/after. Its fixed 120-tree default is intentionally smaller than the active packaged model. Research numbers must be attributed to their own run and cannot be substituted for active API model results.

Generated evidence under `experiments/reports/` includes common-row timestamp hashes, per-fold split boundaries, seeds, feature schemas, parameters, fit durations, Git revision/dirty status, code/config/data/dependency hashes, metrics, seed variation and empirical interval coverage. Source hashes include uncommitted research additions and normalize Python line endings. Optional local MLflow tracking has portable IDs in the JSON report and is absent from the serving dependency path.

The [measured 19 October 2026 research report](experiments/reports/bounded_synthetic_20261019_v5/REPORT.md) selected the full feature group, with mean 2023 validation WAPE 3.8819% and mean fold RMSE 139.32 MW. Its research refit scored WAPE 3.8322% on 8,666 reused historical 2024 one-step targets. Seed-mean WAPE variation for the full group was 0.0019 percentage points (population standard deviation across only three seeds). These measured values describe the bounded research estimator, not the active packaged API model.

The [independent repeat and audit](experiments/reports/bounded_synthetic_20261019_v5/reproduction_check.json) reproduced all compared numeric results exactly on the same locked environment and CPU architecture. Both runs executed 28 fits and 33 local MLflow comparison runs, in 188.891 and 132.032 seconds. The stdlib auditor checked interval counts, common fold timestamps, segment totals/weighted errors, SQLite metrics and active-artifact preservation. These runs capture native `uv.lock`, project metadata and five export hashes after the application version and direct Starlette minimum changed. Existing resolved package versions and predictive sources are retained. Earlier reports remain immutable and numerically identical. This reproducibility evidence does not supply external-data validity.

## Metrics and uncertainty

MAE and RMSE are in MW; WAPE is percentage absolute error divided by total actual demand; bias is mean prediction minus actual demand. R² is undefined for constant-target groups and is exported as null. Segmented reports provide sample counts by hour, month, weekday/weekend and train-defined demand bands, so aggregate accuracy cannot conceal a sparse or difficult segment.

The research interval rule uses a 2023 out-of-fold one-step absolute-residual quantile and √horizon scaling. Coverage/width are measured separately at 1, 6, 24, 72 and 168 hours on twelve fixed monthly origins in reused historical 2024 data. Future demand/weather observations are excluded from each recursive forecast. This heuristic is **not** a nominal-coverage guarantee, and twelve correlated origins give limited evidence. Wide intervals can have high empirical coverage while being of little operational use. The active API's interval estimator has its own calibration scope and must be evaluated separately.

## Known limitations and failure cases

- Synthetic patterns can be easier and more stationary than real demand. Real out-of-distribution changes, outages, extreme weather, social/calendar shifts and sensor faults are unvalidated.
- A small bounded feature study and three seeds cannot establish an optimal architecture or statistical significance. Expanding temporal folds are correlated.
- Sequential one-step evaluation has more recent observations available than a fixed-origin multi-day forecast; their scores measure different tasks.
- Historical weather averages do not anticipate unusual future weather. Scenario weather changes forecast behavior without proving scenario accuracy.
- A 336-hour demand history is required for the full schema. Missing targets are not imputed for scoring; earlier observations may be carried forward only as historical feature inputs.
- Timezone conversion and hourly alignment are explicit. Naive timestamps must already represent the configured local timezone; repeated/ambiguous local hours require upstream resolution.
- No published evaluation demonstrates performance on a real external grid, an independent new period or different customer populations.

Before operational promotion, obtain properly licensed real data with known provenance; freeze an independent future test period; validate input availability at issue time; compare meaningful operational baselines; assess forecast errors and interval coverage across seasons/demand extremes; and maintain monitoring, retraining and rollback procedures. New research runs and real maintenance should be recorded with their actual dates and results.
