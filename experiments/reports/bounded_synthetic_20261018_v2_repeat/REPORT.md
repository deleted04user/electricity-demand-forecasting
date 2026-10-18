# Bounded synthetic research benchmark

Research only. The bundled demand/weather workbook is synthetic. No model artifact is saved or promoted.

Run `20261018T051426Z_f8fd9fe2`; generated 2026-10-18T05:15:11.639473+00:00; elapsed 55.33s; fits 28/28.
Git revision `59be0d4718bdec2f1d3071e9e57832ce3e432aeb`; dirty at execution: `True`. Exact source/config/data/lock hashes are in `report.json`.

## Declared comparison

Three expanding 2023 folds use common timestamps and fixed 120-tree, depth-4 XGBoost settings. One-step predictions use demand and weather observed through the preceding hour. Baselines use observed demand at lags 24 and 168. These are sequential one-step comparisons.

| Variant | Seed | Folds | Mean fold WAPE (%) | Mean fold RMSE (MW) |
| --- | ---: | ---: | ---: | ---: |
| full | 42 | 3 | 3.8819 | 139.32 |
| full | 43 | 3 | 3.8773 | 139.23 |
| full | 44 | 3 | 3.8797 | 139.39 |
| lags | 42 | 3 | 4.0864 | 146.69 |
| lags | 43 | 3 | 4.0793 | 146.53 |
| lags | 44 | 3 | 4.0792 | 146.48 |
| lags_calendar | 42 | 3 | 3.8868 | 139.61 |
| lags_rolling | 42 | 3 | 4.0551 | 145.66 |
| lags_weather | 42 | 3 | 4.0747 | 146.28 |
| naive168 | 42 | 3 | 5.0384 | 181.22 |
| naive24 | 42 | 3 | 6.1641 | 223.80 |

The selected learned variant is **full**, chosen exclusively by seed-42 mean 2023 fold WAPE, with RMSE as tie-breaker. Repeats 43/44 were predeclared for lags and full; their outcomes do not change selection.

| Repeated variant | Seeds | Mean WAPE (%) | Population SD across seed means | Range (%) |
| --- | --- | ---: | ---: | --- |
| lags | 42,43,44 | 4.0816 | 0.0034 | 4.0792–4.0864 |
| full | 42,43,44 | 3.8796 | 0.0019 | 3.8773–3.8819 |

## Reused historical 2024 diagnostics

The repository already used 2024 in prior evaluation/promotion work. It is not an untouched final test. The chosen research variant is refit through 2023; 2024 diagnostics never select features or parameters.

Sequential one-step rows: 8666; WAPE: 3.8322%; RMSE: 140.79 MW. `segmented_errors.csv` reports MAE/RMSE/WAPE/bias/R² and sample counts by month, hour, weekend and demand band. Demand-band boundaries come from training quartiles.

## Interval coverage by recursive horizon

Intervals use the 90th percentile of selected-variant 2023 out-of-fold absolute one-step errors, multiplied by sqrt(horizon). They are a heuristic, not horizon-calibrated conformal guarantees. Twelve predeclared monthly origins forecast recursively for 168 hours. Future weather is replaced by month/hour averages fitted strictly before each origin; future measured weather and demand are excluded.

| Horizon (h) | Origins | Nominal coverage | Empirical coverage | Mean width (MW) | RMSE (MW) |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 12/12 | 90% | 100.0% | 458.41 | 103.69 |
| 6 | 12/12 | 90% | 100.0% | 1122.87 | 145.27 |
| 24 | 12/12 | 90% | 100.0% | 2245.73 | 125.60 |
| 72 | 11/12 | 90% | 100.0% | 3889.72 | 90.26 |
| 168 | 12/12 | 90% | 100.0% | 5915.10 | 137.81 |

Observed undercoverage at horizons: none in this small sample. Counts show scored/planned origins; unavailable actual demand is excluded without imputation. Wide intervals can cover most observations while providing little decision value. Twelve correlated origins have substantial sampling uncertainty; no coverage certification is implied.

## Limitations and reproduction

Synthetic data cannot establish operational forecasting accuracy, customer value or generalization to real Moroccan grid demand. Fixed small tree counts are a bounded feature study, not a production hyperparameter optimization. Correlated temporal folds and only three seeds limit inference. Sequential one-step and fixed-origin recursive results measure different tasks. A new independent real period is required before an unbiased final-performance claim.

See `docs/EXPERIMENTS.md` for hash-locked installation and exact commands. `runs.csv` contains per-fold splits, feature lists, seeds, parameters, row hashes, fit durations and metrics. `report.json` is the portable source of this narrative. Timing, generated IDs, Git status and MLflow IDs may differ between reproductions; numeric metrics should match within the declared tolerance.
