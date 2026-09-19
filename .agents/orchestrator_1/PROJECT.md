# Project: Foresight Phase 3A Analytics Suite

## Architecture
Foresight's Phase 3A Analytics Suite extends the backend with automated tabular feature engineering, fast-fit forecasting, statistical hypothesis evaluation, chart orchestration, and RESTful API endpoints, operating with ephemeral in-memory lifecycles and strictly controlled model artifact sizes (< 50MB).

```
Client Upload / API Request
           │
           ▼
[analytics_router.py] (/api/v1/forecast, /api/v1/hypotheses)
   │ (ephemeral_processing context, max_upload_bytes guardrail)
   ├─► [loader.py] (in-memory BytesIO decoding: CSV, TSV, XLSX, Parquet, UTF-8/Latin-1)
   │
   ├─► [feature_pipeline.py] (date inference, freq detection, lag/rolling windows, expanding mean encoding, leakage pruner)
   │        │
   │        ▼
   ├─► [forecast_engine.py] (Ridge baseline + fast XGBoost max_depth<=7, holdout validation, recursive point/interval forecasting)
   │        │
   ├─► [hypothesis_engine.py] (Welch's t-test equal_var=False, ANOVA, Holm-Bonferroni correction, Cohen's d, non-parametric checks)
   │        │
   └─► [chart_picker.py] (line_chart, bar_comparison, scatter_cluster, kpi_card; deterministic heuristics + Gemini 3.8 Flash)
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | In-Memory Tabular Loader | Decodes CSV, TSV, XLSX, Parquet from RAM bytes with UTF-8/Latin-1 fallback; raises 415 on bad extension. | M1 | Survey |
| 2 | Automated Date Inference & Formatting | Regex/dtype detection of date column, day-first vs month-first inference. | M1 | Survey |
| 3 | Multi-Frequency Resampling & Aggregation | D, W, M, Q frequency detection and calendar aggregation. | M1 | Survey |
| 4 | Target Leakage & Component Pruner | Pruning identical columns, near-duplicates (|r| > 0.9999), and exact pair-sums (e.g. casual+registered). | M1 | Survey |
| 5 | Retail Transaction Log Aggregator | UCI Online Retail log aggregation, cancellation exclusion, bad price filtering, Saturday gap zero-filling. | M1 | Survey |
| 6 | Leakage-Safe Calendar & Temporal Features | Sin/cos cyclical features, lag features, rolling window statistics on shifted target. | M1 | Survey |
| 7 | Out-of-Fold Expanding Mean Encoding | Cumulative mean encoding with smoothing m=10.0 excluding current row target. | M1 | Survey |
| 8 | Dynamic Fast-Fit Forecasting | Ridge baseline + XGBoost (max_depth<=7) holdout validation and recursive forecasting. | M2 | Survey |
| 9 | Pre-Trained Model Lazy Loader | ModelRegistry lazy loading and in-memory caching for sub-100ms inference. | M2 | Survey |
| 10 | Target Log-Transformation & Non-Negativity | Log1p training for non-negative targets with expm1 inversion and clipping at 0. | M2 | Survey |
| 11 | Welch's Two-Sample t-Test Engine | scipy.stats.ttest_ind(equal_var=False), reporting lift %, Cohen's d, t-stat, p-val. | M2 | Survey |
| 12 | One-Way ANOVA & Multiple Comparisons | scipy.stats.f_oneway for 3+ groups with eta-squared effect size. | M2 | Survey |
| 13 | Non-Parametric Validation & Skewness Check | Mann-Whitney U / Kruskal-Wallis cross-checks and |skew|>2 warnings. | M2 | Survey |
| 14 | Holm-Bonferroni P-Value Adjustment | Step-down family-wise error rate control at alpha=0.05. | M2 | Survey |
| 15 | POST /api/v1/forecast Endpoint | Multipart upload endpoint returning predictions, actuals, holdout metrics, recommended visualization. | M3 | Survey |
| 16 | POST /api/v1/hypotheses Endpoint | Multipart upload endpoint returning statistical tests, lift %, p-values, recommended visualization. | M3 | Survey |
| 17 | Deterministic Heuristic Chart Picker | Rules mapping forecast -> line_chart, hypotheses -> bar_comparison, segmentation -> scatter_cluster. | M3 | Survey |
| 18 | Gemini LLM Visualization Recommender | Async Gemini 3.8 Flash recommender using anonymous metadata only, falling back to heuristics on error. | M3 | Survey |
| 19 | Ephemeral Memory Lifecycle Governance | Memory clearing via sys._getframe(1), dereferencing locals to None, gc.collect() in finally block. | M4 | Survey |
| 20 | Model Artifact Footprint Governance | Strict adherence to < 50.0 MB ceiling (joblib compress=3), audited via audit_artifact_size.py. | M4 | Survey |
| 21 | Test Suite & Zero Regression Safety | 205 tests passing (180+ Phase 2 regression baseline, Phase 3A unit & real benchmark tests). | M4 | Survey |
| 22 | Continuous Documentation & README | Full documentation of Phase 3A design, endpoint schemas, and test run results in README.md. | M4 | Survey |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Pipeline & Loader Latency Tuning | Verify R1 feature pipeline and data loader; tune XGBoost hyperparameters (n_estimators=30, max_depth=4, learning_rate=0.08, subsample=0.9, colsample_bytree=0.9, tree_method="hist", max_bin=64, n_jobs=2) and Gaussian warmup in `forecast_engine.py`. Align pyproject.toml. | none | DONE |
| M2 | Test Suite Verification & Regressions | Run complete test suite (`pytest backend/tests/test_phase3a.py`, `pytest backend/tests/test_phase3a_real_data.py`, and full `pytest backend/tests/`). Confirm 224/224 tests pass with 0 regressions. | M1 | DONE |
| M3 | Artifact Footprint Audit & Governance | Run `python backend/scripts/audit_artifact_size.py`. Verify all models in `backend/models/` and `models/` remain strictly < 50.0 MB (2.53 MB total, 5.1% utilization). Confirm ephemeral memory lifecycles. | M2 | DONE |
| M4 | README.md Documentation & Living Log | Update `README.md` with complete Phase 3A architecture, endpoint documentation, mathematical specifications, tuning results, and test run verification logs per AGENTS.md §6. | M3 | DONE |
| M5 | Multi-Agent Audit & Gate Review | Reviewer, Challenger, and Forensic Auditor verification. Gate pass check. | M4 | DONE |

## Interface Contracts
### `backend/src/analytics/loader.py` ↔ `backend/src/api/analytics_router.py`
- `load_tabular(raw: bytes, filename: str) -> pd.DataFrame`
  - Decodes in-memory byte stream via `io.BytesIO`.
  - Supported extensions: `.csv`, `.tsv`, `.txt`, `.xlsx`, `.xls`, `.parquet`.
  - Encoding fallback: UTF-8 -> Latin-1.
  - Raises: `UnsupportedFormat` (415), `EmptyFileError` (400), `ParseError` (422).

### `backend/src/analytics/feature_pipeline.py` ↔ `backend/src/analytics/forecast_engine.py`
- `prepare_series(df: pd.DataFrame, target: Optional[str] = None, date_col: Optional[str] = None, freq_hint: Optional[str] = None) -> PreparedSeries`
  - Returns `PreparedSeries(y, exog, dates, freq_cfg, preprocessing_metadata)`.
  - All temporal features strictly shifted to avoid forward target leakage.

### `backend/src/analytics/forecast_engine.py` ↔ `backend/src/api/analytics_router.py`
- `run_forecast(prep: PreparedSeries, horizon: Optional[int] = None) -> dict`
  - Returns dictionary with `status`, `series`, `holdout`, `forecast`, `metrics`, `timing_ms`.
  - Timing: `compute_total` within budget (< 200ms in tests, < 100ms target).

### `backend/src/analytics/hypothesis_engine.py` ↔ `backend/src/api/analytics_router.py`
- `run_hypotheses(df: pd.DataFrame, target: Optional[str] = None, group_cols: Optional[list[str]] = None) -> dict`
  - Returns dictionary with `status`, `target`, `tests`, `timing_ms`.
  - Performs Welch's t-test (`equal_var=False`), ANOVA, Holm-Bonferroni correction, Cohen's d.

### `backend/src/orchestrator/chart_picker.py` ↔ `backend/src/api/analytics_router.py`
- `pick_chart(kind: str, facts: dict, settings: Settings) -> dict`
  - Returns `{"chart": ..., "reason": ..., "source": ..., "allowed": [...]}`.
  - Allowed: `("line_chart", "bar_comparison", "scatter_cluster", "kpi_card")`.

## Code Layout
- `backend/src/analytics/`:
  - `loader.py`: In-memory tabular dataset loader.
  - `feature_pipeline.py`: Leakage-safe feature engineering pipeline.
  - `forecast_engine.py`: Ridge + XGBoost forecasting engine with recursive predictor.
  - `hypothesis_engine.py`: Welch's t-test and ANOVA statistical testing engine.
- `backend/src/api/`:
  - `analytics_router.py`: FastAPI endpoints for `/api/v1/forecast` and `/api/v1/hypotheses`.
- `backend/src/orchestrator/`:
  - `chart_picker.py`: Visualization recommendation engine.
- `backend/config/`:
  - `settings.py`: Pydantic settings and configuration parameters.
- `backend/tests/`:
  - `test_phase3a.py`: Unit and integration test suite for Phase 3A components.
  - `test_phase3a_real_data.py`: Benchmark dataset tests on real data.
  - `conftest.py`: Fixtures and dataset generators.
- `backend/scripts/`:
  - `audit_artifact_size.py`: Model artifact size verification script.
- `README.md`: Project documentation and living log.
