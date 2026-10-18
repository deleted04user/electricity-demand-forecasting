# Reproduce the bounded research benchmark

The experiment command is an offline research tool. It uses only the bundled **synthetic** workbook and never saves, promotes or replaces a model. Serving works without MLflow. The existing production-training prohibition for synthetic data remains in place.

The [executed benchmark report](../experiments/reports/bounded_synthetic_20261018_v2/REPORT.md) and [portable JSON](../experiments/reports/bounded_synthetic_20261018_v2/report.json) record the measured run on 18 October 2026: 28 fits, 33 tracked fold comparisons and 59.5 seconds. The selected full feature set obtained mean 2023 fold WAPE 3.8819%, versus 4.0864% for lags, 5.0384% for weekly naive and 6.1641% for daily naive. These are synthetic one-step comparisons, not operational accuracy claims.

An [independent repeat](../experiments/reports/bounded_synthetic_20261018_v2_repeat/REPORT.md) completed in 55.329 seconds with identical code/config/data/lock identities. The [reproduction check](../experiments/reports/bounded_synthetic_20261018_v2/reproduction_check.json) records a maximum numeric difference of **0.0**, against tolerance 0.0001, across ablation comparisons, seed variation and historical diagnostics. A separate standard-library audit recomputed coverage directly from CSV boolean counts, verified segment totals/common fold timestamps, checked that both local SQLite databases contain the 33 reported finished MLflow runs, and confirmed the active model hash remained unchanged.

## Install a locked environment

From the repository root, with Python 3.12 and `uv` installed:

```powershell
uv venv --python 3.12 .venv-research
uv pip sync --python .venv-research/Scripts/python.exe --require-hashes requirements-research.lock.txt
.venv-research/Scripts/python.exe -m backend.experiments --config configs/experiments.json --output experiments/reports/my-reproduction --mlflow
```

On Linux/macOS use `.venv-research/bin/python` in place of `.venv-research/Scripts/python.exe`. A standard Python virtual environment and `python -m pip install --require-hashes -r requirements-research.lock.txt` work too. The lock includes API/development requirements and the small MLflow client distribution plus SQLite dependencies; it does not install the full MLflow serving stack.

The output must be a **new** directory below `experiments/reports`; existing runs cannot be overwritten through the public command. Omit `--mlflow` to create the same portable JSON/CSV reports without tracking; `requirements-dev.lock.txt` is sufficient for that mode. Offline describes execution after dependencies have been installed; package installation needs a package index or a local wheel cache.

## Predeclared protocol

The versioned [configuration](../configs/experiments.json) is validated before fitting. Arbitrary remote data, undeclared folds, feature sets, seeds, selection criteria and model parameters are rejected. Tree/thread/time limits may be lowered for smoke runs; the generated report records the actual settings.

| Fold | Expanding training through | Validation period |
| --- | --- | --- |
| 2023_jan_apr | 2022-12-31 23:00 | January–April 2023 |
| 2023_may_aug | 2023-04-30 23:00 | May–August 2023 |
| 2023_sep_dec | 2023-08-31 23:00 | September–December 2023 |

All seven comparisons use the same validation timestamps, dropping rows unavailable for **any** full feature. Calendar information is known in advance; demand lags and rolling statistics use only preceding observations. For these research comparisons, temperature/humidity are shifted one hour, with forward fill from earlier observations only. Thus a sequential one-step prediction at hour *t* uses observations through *t−1*. Later validation rows may use demand observed after earlier validation predictions; this explicitly measures one-step operation, not a forecast of the entire fold from its first hour.

The learned variants are lags, lags+weather, lags+calendar, lags+rolling, and all features. Fixed 24-hour/168-hour naive baselines are reported on identical rows. All learned variants start with seed 42. The lags and full comparisons are predeclared for repeats 43/44 regardless of who wins. Those repeat results describe variation and never change feature selection. The learned variant with lowest mean seed-42 fold WAPE wins, with RMSE and then its name as deterministic tie-breakers. Baselines provide context; selection is explicitly among the five learned variants and does not imply that a learned model necessarily beats a naive baseline.

The default budget is **28 fits, 120 trees per fit, depth 4, two CPU threads, and 300 seconds**. Fifteen initial fits plus twelve repeated fits leave one research-only refit on data through 2023. The CLI supervises a separate worker with a hard wall-clock timeout, and the worker checks its fit/time budget between operations. Thread limits are also set for OpenMP/OpenBLAS/MKL. Timeout, nonfinite predictions or changing code/data/config/locks refuse a successful report. Very slow machines can time out; they should lower tree count or use a faster machine, not silently increase the scientific search.

## Historical error and interval diagnostics

The repository used 2024 in earlier evaluations and promotion decisions. Consequently the report labels every further 2024 result **reused historical diagnostics**, never an untouched final test. No 2024 metric determines the selected variant, parameters, interval radius or demand-band boundaries.

The selected research variant is refit through 2023 and evaluated sequentially on available 2024 rows. `segmented_errors.csv` includes counts and MAE, RMSE, WAPE, bias and R² by month, hour, weekday/weekend and demand band. Low/middle/high demand boundaries use the refit's training-demand 25th/75th percentiles. Constant-target segments have undefined R², serialized as JSON null/blank CSV.

Recursive predictions begin at the first hour of each month in 2024. Forecasts use only demand observed before that origin, then feed predictions back into lag/rolling features. Their weather input is the last observed hour at step 1, then month/hour historical averages fitted strictly before the origin. Actual post-origin weather is excluded. Coverage is measured at horizons 1, 6, 24, 72 and 168 hours, with 12 planned origins each. An unavailable measured target remains null and is excluded from scoring; the report shows scored/planned counts and missing-target counts. Targets are never imputed for scoring.

The interval rule is predeclared: the higher empirical 90th percentile of the selected variant's **2023 out-of-fold one-step absolute errors**, multiplied by √horizon, with the lower bound clipped to zero. These are the same validation folds used for feature selection, so this is not an independent calibration sample. This is a heuristic whose uncertainty grows with horizon. It is not horizon-specific conformal calibration. The report shows actual coverage and width, including undercoverage, and cautions that twelve correlated origins cannot certify 90% coverage. These research intervals characterize a separate bounded model; they do not validate the active API model's intervals.

## Outputs and provenance

| Artifact | Contents |
| --- | --- |
| `REPORT.md` | Generated interpretation and limitations |
| `report.json` | Protocol, package versions, seeds, comparison metrics, variation, refit and historical summaries |
| `runs.csv` | 33 per-fold comparison rows; boundaries, counts, common-timestamp hash, feature schemas, parameters, durations and metrics |
| `segmented_errors.csv` | Historical one-step errors and sample counts by segment |
| `interval_predictions.csv` | Per-origin/horizon actual, prediction, bounds, width and coverage |
| `mlflow.db`, `mlflow_artifacts/` | Optional local tracking database and artifacts; ignored in Git |

Portable reports record Git revision and dirty status for tracked repository files. Untracked user files are excluded from Git status output. Content hashes capture newly added research code as well as features, ingestion, modeling and dependency locks. Python source hashes normalize CRLF to LF; workbook/config/lock hashes are byte-exact SHA256. A combined source-manifest digest and data/config hashes identify the exact measured implementation even when a run is generated before its commit. The worker verifies these inputs again before writing success. Git status may change due to unrelated documentation work while running; research inputs may not change.

The active artifact hash is recorded before and after; a mismatch refuses success. No experiment estimator is serialized. IDs and timings differ between reproductions. With identical locked packages and CPU architecture, numeric metrics should reproduce within an absolute tolerance of **0.0001**; differing architectures/library builds require investigating measured differences before claiming equivalence.

With `--mlflow`, the runner explicitly selects SQLite inside its output directory, ignoring inherited remote tracking URI configuration. It disables MLflow usage telemetry and OTLP trace exports before import. Optional imports/database initialization are checked before any model fit, so a missing research dependency fails immediately. It writes local artifacts only and logs the same per-fold parameters/metrics/provenance. `report.json` exports the portable run-ID ↔ MLflow run-ID mapping, so inspection does not depend on retaining the database. For local database browsing and API behavior, see the official [local tracking tutorial](https://www.mlflow.org/docs/latest/ml/tracking/tutorials/local-database/), [tracking API](https://mlflow.org/docs/latest/ml/tracking/tracking-api/) and [telemetry controls](https://mlflow.org/docs/latest/community/usage-tracking/).

## Interpretation

The synthetic benchmark provides reproducible engineering evidence about this specific workbook. It establishes neither real-grid accuracy nor a market valuation. Tree counts are intentionally bounded, only three seeds are sampled, folds share expanding training data, 2024 has been reused historically, and long-range recursive errors compound. An independent real operational dataset and genuinely new period are needed before deployment-performance claims. See [MODEL_CARD.md](../MODEL_CARD.md).

In the published run, reused historical 2024 diagnostics contain 8,666 observed one-step targets, with WAPE 3.8322% and RMSE 140.79 MW. All observed interval targets were covered in the small monthly-origin sample: 12/12 at horizons 1, 6, 24 and 168; 11/11 at horizon 72, where the twelfth actual target is missing. Mean widths grow from 458.41 MW at one hour to 5,915.10 MW at 168 hours. That combination illustrates the interval heuristic's conservatism and limited usefulness at long horizons; it does not certify 90% future coverage.
