# Quality improvement plan and assessment evidence

## Current round — 19 October 2026

The new public assessment displays **80 (B)** and estimates $120, subject to
review. It does not expose the analyzed commit or an authoritative decimal
score. This round aims to improve the documented weak dimensions as far as the
project's real scope supports; no implementation can guarantee a score near 100.

| Finding | Focused response | Acceptance evidence |
| --- | --- | --- |
| Python lockfiles not detected | Adopt a native `uv.lock` as the actual resolved graph; generate all five hash exports from it | Byte-for-byte export guard, native locked installs on Linux/Windows, pip-installed Docker API and audits of every export |
| Thin analytics-page coverage | Test rendered demand/correlation values, real diagnostic baseline/horizon rows, HTTP/network/JSON failures | Full frontend lint, 25 component tests and production build, plus existing live-browser scenarios |
| Unexpected failures only in local logs | Add optional lifespan-owned Sentry reporting with strict event allowlist and no automatic PII/request capture | Real SDK in-memory transport tests, default-off/runtime-isolation and failure-path regressions |
| Security model/tooling is limited | Formalize local trust boundaries and residual risks; CodeQL scans Python, JavaScript and Actions | Security workflow results, private reporting, repository secret scanning/push protection and existing dependency audits |
| Container resources/startup undocumented | Measure readiness time and idle Docker CPU/memory, verify JSON readiness/provenance through both paths | Revision-specific container evidence, real Docker/browser CI and failure-guard tests |
| Legacy dashboard allegedly duplicates algorithms | Retain shared backend imports and document separate optional environment | Existing shared implementations; legacy packages remain outside the API lock/image |
| Short, single-author history | Keep real features/fixes with their tests in focused commits; sustain useful work over time | Actual Git history and review findings; no manufactured contributors, dates or filler commits |

Before release, review each changed area twice, resolve findings, run the full
supported checks and repeat the frozen research study with the new dependency
provenance. Preserve the prior reports and active model unchanged. Publish a
tested release with measured evidence after all required jobs pass. Request the
next public assessment only after DataFactor's once-per-day cooldown, using the
already authorized report address; record the actual new score separately from
engineering evidence. Use any new genuine deductions to choose further work.

The detailed original plan below records the earlier baseline and completed
architecture/research work; its descriptions of former gaps are historical.

## Original plan — 17–18 October 2026

Prepared 2026-10-17; implementation updated 2026-10-18. Architecture, research, browser integration and release evidence are implemented. Final release validation and the external assessment are tracked below. Target: an evaluator-confirmed score above 80; aim for 85 to allow some margin. The evaluator's weights and eligibility rules are unknown, so engineering checks cannot guarantee a numerical score or an offer.

## 1. Establish the correct baseline first

The latest supplied assessment gives an overall 62.7, while repeating the earlier category scores and claims of four commits, no Python lock, no Docker, and no lint/type/coverage/audit enforcement. These claims conflict with the published code inspected for this plan.

Verified code baseline: `d595a2d6abd87d954891183d61b699dc19b795dc`, with 12 commits at that revision. [Its Quality workflow passed all five jobs](https://github.com/deleted04user/electricity-demand-forecasting/actions/runs/39077873426).

| Assessment claim | Published evidence at the verified baseline |
| --- | --- |
| No Python lockfile | `requirements-api.lock.txt`, `requirements-dev.lock.txt`, and `requirements.lock.txt`, with pinned versions and hashes |
| No container setup | Root and frontend Dockerfiles, `docker-compose.yml`, and a successful container build/start/proxy smoke test |
| No lint or type checking | Ruff lint/format and mypy steps in `.github/workflows/quality.yml` |
| No coverage enforcement | Branch coverage enabled and a 75% floor in `pyproject.toml`; the verified local run achieved 93.93% |
| No dependency audit or updates | Python and npm audit jobs, plus `.github/dependabot.yml` |
| No runnable suite | 76 passing backend tests, 16 passing frontend tests, and Windows/Linux backend CI |
| No health endpoint or logging | `/api/health` and JSON request/error logs in `backend/logging_config.py` |
| No onboarding files | Root/frontend environment examples, `CONTRIBUTING.md`, and `CHANGELOG.md` |

First action: request a fresh scan of the current `main` and ask the evaluator to include the commit SHA and scan time. If it reports these items missing at the correct SHA, investigate artifact detection before repeating completed work. Provide direct file links and the successful workflow as evidence.

Suggested message to the evaluator:

> Please rescan the latest main branch and include the analyzed commit SHA and scan time. The report still describes four commits and missing lockfiles, Docker, and CI checks. Those features are present in code revision d595a2d6abd87d954891183d61b699dc19b795dc, whose five CI jobs passed. Please refresh the repository analysis and confirm the minimum source-volume and task-capacity requirements for eligibility.

This message is a draft; it has not been sent. The website's stated priority-review window is 30 days from submission. Confirm that date rather than assuming it starts with this plan.

**Exit gate:** an assessment tied to the correct commit, or confirmation that detection needs correction. Implementation of the genuine gaps below can proceed while awaiting that response.

## 2. Improve architecture and failure handling

Estimated effort: 1-2 focused working days. The supplied report assigns this area up to about six points; that is the evaluator's approximate ceiling, not a promised gain.

Current concrete gaps: `backend/main.py` loads data and the model during module import, exposes shared global state, and computes expensive evaluation diagnostics from a request path. `backend/evaluate.py` imports the API module and inherits that startup work.

Deliver work in focused changes with regression tests:

1. Introduce a small settings object, application factory, and prediction service. Move resource loading into the application's lifespan. Let evaluation use the shared service without importing the HTTP application. Preserve existing endpoint contracts and model results. FastAPI documents [lifespan handling for shared ML resources](https://fastapi.tiangolo.com/advanced/events/).
2. Define readiness explicitly: distinguish a running process from usable model/data. Return a documented unavailable response when required resources fail validation. Validate artifact keys, feature order, compatible history, and trusted manifest checksums; continue loading only trusted serialized artifacts.
3. Test missing/corrupt artifacts, incompatible feature schemas, empty histories, insufficient evaluation rows, and non-finite response values. Exercise initialization and shutdown as well as normal requests.
4. Compute or cache diagnostics against the model/data identity so ordinary dashboard requests do not repeatedly initiate full recursive backtests. Invalidate derived results when their inputs change.

**Exit gates:** importing API/evaluation modules does not load the dataset or model; all seven existing endpoints retain their documented behavior; initialization failures have predictable diagnostics; service instances can be tested independently; cache tests demonstrate that changed inputs cannot reuse stale results.

## 3. Make ML experiments independently reproducible

Estimated effort: 2-3 focused working days, with a bounded experiment runtime agreed before execution. The report assigns this area up to about six points.

Existing seeds, folds, candidate reports, and hashes are useful foundations. Add an explicit experiment workflow and interpretable analysis:

1. Add checked-in experiment configuration describing the dataset contract, feature groups, chronological folds, seeds, metrics, CPU/thread limits, and maximum fits. Keep research dependencies in a separate hashed lock.
2. Add local experiment tracking using an optional research installation of [MLflow](https://mlflow.org/docs/latest/ml/tracking/). Export portable JSON/CSV summaries too. Record run ID, Git SHA/dirty status, data hash, dependency-lock hash, feature schema, parameters, split boundaries, seed, duration, and metrics. The serving application must work without a tracking server.
3. Run a predeclared ablation study: naive baselines, demand lags only, lags plus weather, lags plus calendar, lags plus rolling statistics, and the full feature set. Compare on common timestamps with the same evaluation rules. Start with one fixed seed; repeat the selected comparisons with two additional seeds to report variability.
4. Report MAE/RMSE/WAPE/bias by month, hour, weekday/weekend, and demand band, with sample counts. Separate observed-lag evaluation from recursive horizons of 1, 6, 24, 72, and 168 hours.
5. Measure empirical prediction-interval coverage and width by horizon. Document undercoverage where it occurs rather than implying that a nominal 90% interval guarantees 90% coverage.
6. Add a model card and generated experiment report describing provenance, failure cases, limitations, and exact reproduction commands.

The bundled dataset must remain labeled synthetic. A separate research-only benchmark may use it without permitting production artifact promotion. Preserve the existing training guard. Keep the active artifact unchanged during these experiments.

The 2024 period has already been used for evaluation and promotion decisions. Further analyses of it are historical diagnostics, not a new untouched final test. Select ablations on the declared validation folds; obtain a genuinely independent period before claiming a new unbiased final result.

**Exit gates:** another clean environment reproduces the tables within a tolerance declared before comparison; every result identifies its code/data/configuration; tests verify chronological separation and no future information in features; no research command overwrites the active model.

## 4. Turn the existing quality checks into stronger release gates

Estimated effort: 0.5-1 working day, after architecture changes settle.

- Raise the enforced branch-coverage floor from 75% to 90%, backed by meaningful failure-path tests. The current baseline already exceeds 90%; retain that level through the changes. Make the threshold explicit in CI and configuration.
- Give new settings, service, artifact, and response boundaries precise types. Enable strict mypy checks for those modules; expand enforcement only when their dependencies are accurately typed. Avoid broad error suppression.
- Add one real browser integration scenario against the containerized API: load the dashboard, request a forecast, and display a controlled API failure. Keep the existing fast component tests.
- Update GitHub Actions that report deprecated runtimes, use a deliberately selected runner image, and set reasonable job timeouts. Verify both supported operating systems and the container stack again after changes.
- Keep dependency locks synchronized and all audits passing. Ensure the optional research lock is also audited.
- Publish a compact quality-evidence document linking the relevant files, exact tested commit, workflow, coverage artifact, and fresh-clone commands. Use generated evidence rather than manually claiming passing results.

**Exit gates:** all CI jobs pass on the proposed release commit; branch coverage is at least 90%; lint/types pass; audits report no known vulnerabilities; a fresh clone can install, test, build, and serve the dashboard; the browser scenario passes against real services.

## 5. Build the history and maintenance evidence

Start with the implementation above; continue through useful work over the following 2-4 weeks. The report assigns history up to about seven points, but elapsed time and commit count do not establish a guaranteed score.

- Keep each actual bug fix or feature with its proving tests in the same commit or focused PR. Describe the trigger, resulting behavior, and validation.
- Use real review feedback, issue reproduction, and dependency-update work as it occurs. Resolve failures and record the evidence.
- Create a versioned release with accurate release notes after the release gates pass. Include reproduction instructions and links to artifacts.
- Invite independent review when available; attribute actual contributions to their authors. Do not backdate changes, invent contributors, or split trivial edits to inflate history.
- Continue with improvements supported by findings: measured diagnostic caching, documented model compatibility checks, or a verified external-data integration. Avoid adding unrelated functionality or code solely to increase volume.

**Exit gate:** the history shows understandable changes with tests, validation, and genuine maintenance over time. Request the buyer's actual task-capacity/minimum-volume requirements; a quality score alone may not satisfy those rules.

## 6. Submission and decision gates

1. Obtain the corrected scan now; preserve its commit SHA and category breakdown.
2. Complete architecture and reproducibility work, then enforce all release checks.
3. Submit the exact tested revision with the evidence document, experiment report, model card, and release notes. Ask for an updated category breakdown and task-capacity assessment.
4. If the score is below 80, address the specific deductions in that new report. Do not infer progress from commit totals or add the advertised point ceilings together.
5. Record success only when an actual assessment of that revision exceeds 80. Treat an offer as a separate result subject to the buyer's review.

The supplied 62.7 would need more than 17.3 additional points to exceed 80. Its advertised maximum gains sum to 19, which would yield 81.7 only if all were awarded without overlap or other changes. That is too narrow and uncertain to serve as a guarantee. The practical strategy is to fix the stale baseline, strengthen the documented weak areas, keep a margin in the engineering gates, and verify the external result.

## Proposed execution sequence

| Stage | Deliverable | Dependency |
| --- | --- | --- |
| First | Correct-commit rescan request and evidence links | Existing published baseline |
| Next | Lifecycle/service boundary and initialization tests | Existing API behavior captured by tests |
| Next | Readiness/artifact validation and diagnostic caching tests | Service boundary |
| Next | Configured experiment runner, tracking, and leakage tests | Shared evaluation service |
| Next | Ablation/error/interval reports and model card | Reproducible runner and declared protocol |
| Next | Stronger CI gates and container browser integration | Stable implementation |
| Release | Evidence document, release notes, final clean-clone validation | All gates passing at one revision |
| Ongoing | Useful maintenance and genuine review | Findings and user feedback |
| Verify | New external assessment above 80 | Correct tested revision submitted |

Planning estimate: approximately 4-7 focused engineering days, plus the maintenance period where the buyer requires it. Adjust the sequence using the corrected scan; already-satisfied requirements do not need to be rebuilt.

## Implementation record — 18 October 2026

- Service ownership, managed startup, readiness/liveness, trusted artifact verification, timezone isolation, typed responses and identity-checked prepared diagnostics are implemented and covered by failure-path tests.
- The bounded research protocol has executed on the synthetic workbook, including three chronological folds, feature ablations, seed repeats, segmented errors, interval diagnostics and local MLflow tracking. The [measured report](experiments/reports/bounded_synthetic_20261018_v3/REPORT.md) and [model card](MODEL_CARD.md) preserve its scope and limitations. The serving model is unchanged.
- The v0.2.0 local full backend run passed 172 tests with 95.37% branch-aware coverage. The enforced floor is now 90%. Frontend lint, 17 component tests, build and dependency audit passed; six repeated Chromium scenarios exercised real forecast and recovery behavior.
- Independent review examined runtime lifecycle and artifacts, research leakage and missing targets, interval arithmetic, and browser/container integration. Review findings were fixed and tested before publication.
- [QUALITY_EVIDENCE.md](QUALITY_EVIDENCE.md) maps implementation to tests, reports and CI artifacts. The release checks run on Linux/Windows and exercise the Docker stack in Chromium. Final commit-specific CI, fresh-clone validation and the external score must be verified at publication.

Longer maintenance history and any buyer-specific source-volume requirement remain external eligibility factors. This implementation does not manufacture elapsed history, contributors or a score.

The first fresh public-copy assessment returned **79.5 (B)** on 18 October 2026, a measured increase of 16.8 points from the supplied 62.7. The website rounded it to 80; the emailed report supplied the precise value, so the target remains unmet. Release v0.2.0 passed all five CI jobs and independent fresh-clone validation. A follow-up corrects scanner-visible dependency metadata, the Pydantic 2 contract, environment documentation and Compose-file discoverability. The target of exceeding 80 requires a subsequent external result; genuine maintenance over time remains ongoing work.
