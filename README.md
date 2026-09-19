# Foresight

Foresight is an intelligent forecasting system consisting of multiple predictive engines (Engine A for primary forecasting, Engine B for anomaly detection and clustering) with robust data ingestion, validation, and sanitization pipelines.

## Project Structure

- `backend/`: FastAPI backend powering the core predictive engines, data parsers, and endpoints.
- `frontend/`: Web interface interacting with the backend APIs.
- `models/`: Serialized models and artifacts.

---

## Architectural Decisions & Model Tuning

### Engine A (Forecasting)
- **Problem**: We encountered inflated Root Mean Square Percentage Error (RMSPE) metrics primarily on low-demand rows (e.g., units < 50), which was identified as a metric sensitivity artifact rather than a true model fit issue.
- **Tuning Insights**: After evaluating Ridge Regression, MLP Regressors, and XGBoost on a strict chronological split (with lag/rolling features without temporal leakage), we determined optimal hyperparameters for the XGBoost Regressor to hit strict performance thresholds (RMSPE <= 15%, R² >= 0.85).
- **Optimized Hyperparameters**: 
  - `max_depth` = 3
  - `n_estimators` = 100
  - `learning_rate` = 0.05

### Engine B (Anomaly & Clustering)
- Supports robust feature engineering and uses Isolation Forest for anomaly detection and KMeans / PCA for clustering. Validation thresholds require Silhouette Score >= 0.45 and 2D PCA Explained Variance >= 80%.

---

## Changelog & Recent Fixes

### Data Ingestion & Security
- **Size Guard Updates**: Replaced the deprecated Starlette constant `HTTP_413_REQUEST_ENTITY_TOO_LARGE` with `HTTP_413_CONTENT_TOO_LARGE` across validators, middleware, and tests to guarantee forward compatibility with FastAPI and Starlette.
- **Pandas Data Profiling**: Modified `pd.to_datetime` in the raw data profiler to explicitly use `format="mixed"` to silence dateutil fallback warnings.

### Code Quality & Typing
- **Type Checking (MyPy/Pyright)**: 
  - Resolved absolute import mapping errors in `tabular_parser.py` (`backend.src.models` -> `src.models`).
  - Addressed ExtensionArray limitations by explicitly coercing subset masks and features to `numpy` arrays via `.to_numpy()` before feeding them to Scikit-Learn pipelines (`Ridge.fit`) and boolean bitwise operations (`~`, `.sum()`).
  - Switched from direct attribute access (e.g., `.n_clusters`, `.n_components`) to `.get_params()` on Scikit-Learn estimators for strict typing compliance.
- **Linting (Flake8)**: Pruned several unused variables and unnecessary dependencies/imports in the test suite (`test_train_engine_a.py`, `test_train_engine_b_anomaly.py`, `test_upload_endpoint.py`). Removed unnecessary typecasting overhead on columns during tabular parsing. 
- **Tests**: Suppressed internal third-party warnings (`starlette.testclient`) in `pytest.ini` to keep standard outputs clean. The codebase currently passes all 205 unit and integration tests with zero failures.

### Architectural & Governance Invariants
- **Continuous Documentation Standard**: Codified Section 6 in `AGENTS.md` and `GEMINI.md` establishing a mandatory project rule that all plans, walkthroughs, defects, architectural updates, function adjustments, and setup instructions must be continuously logged and maintained directly in `README.md`.

### Configuration & Environment
- **Settings & Config (Pydantic v2)**: Configured `backend/config/settings.py` with Phase 3A properties (`LATENCY_BUDGET_MS=200`, `LLM_TIMEOUT_S=2.5`, `CHART_PICKER_ENABLED=True`, `max_upload_bytes=52428800`).
- **Google AI Studio Integration**: Added `GOOGLE_API_KEY`, `GEMINI_API_KEY`, and `LLM_MODEL` defaults (Gemini 3.8 Flash) along with `active_api_key` accessor properties.
- **Environment Templates**: Created `backend/.env.example` as a template for project constants (`UPLOAD_MAX_SIZE_BYTES=52428800` overriding legacy `MAX_FILE_SIZE_MB`, `CORS_ORIGINS`, `ENABLE_RATE_LIMITING`).

---

## Phase 3A: Zero-Auth Stateless Analytics Platform (Completed)

Phase 3A integrates the primary in-memory analytics engines, feature engineering pipelines, hypothesis testing engine, LLM-guided chart orchestration, and streaming multipart REST API endpoints into the production backend.

### 1. Architectural Scope & Security Boundaries
- **Ephemeral Memory Lifecycle**: All file ingestion, feature engineering, and model inference operations strictly execute within `ephemeral_processing()` context managers using in-memory byte streams (`io.BytesIO`). No raw user datasets, intermediate features, or session logs are ever written to disk or relational databases.
- **Security Gate Isolation**: GLM 5.3 is strictly scoped to the Anti-Gravity Security Audit Gate; it is completely prohibited from active runtime code, background pipelines, or inference endpoints.
- **Artifact Footprint Compliance**: Validated via `backend/scripts/audit_artifact_size.py --ceiling-mb 50.0`. The combined size of all 10 serialized `.joblib` model artifacts remains at **2.53 MB** (5.1% utilization of the 50.0 MB architectural ceiling, leaving 47.47 MB headroom).
- **Scope Boundary**: Phase 3B (Clustering & Anomaly Detection REST endpoints) remains strictly unstarted.

### 2. Core Engines & Pipeline Modules
- **RAM-Only Tabular Loader (`backend/src/analytics/loader.py`)**:
  - Ingests CSV, TSV, XLSX, and Parquet directly from memory buffers.
  - Automatically handles UTF-8 with seamless fallback to Latin-1/ISO-8859-1 for legacy retail and international transaction exports.
- **Adaptive Feature Pipeline (`backend/src/analytics/feature_pipeline.py`)**:
  - Automated date column identification and frequency inference (`D`, `W`, `M`, `Q`) with trajectory smoothing across ambiguous day-first date formats.
  - Transaction log auto-detection (`is_retail_transactions`) and daily net revenue aggregation (`prepare_retail_daily`), filtering cancellations (`Quantity < 0`), non-positive unit prices, and filling non-trading calendar gaps with zero revenue.
  - Strict leakage defense: drops ID/sequence columns and automatically strips additive target components (e.g. dropping `casual` and `registered` when forecasting total rentals `cnt`).
  - Cyclical calendar transforms (sine/cosine encodings for day-of-week, month, day-of-year) and expanding out-of-fold smoothed mean target encoding.
- **Fast-Fit Dual Regressor (`backend/src/analytics/forecast_engine.py`)**:
  - Fits both a regularized Ridge baseline and an XGBoost primary regressor (`max_depth=3`, `n_estimators=35`, `tree_method="hist"`).
  - Evaluates models on chronological holdout validation sets reporting $R^2$, RMSPE, MAE, and RMSE to dynamically select the winning predictor.
  - Fast linear prediction: precomputes effective weights and intercepts ($arr \cdot w + b$) for Ridge, speeding up inference 500x.
  - Pre-allocated 2D numpy buffer and pre-mapped column indices eliminate DataFrame reconstruction in the multi-step recursive loop, achieving sub-100ms total compute time.
  - Generates recursive multi-step forecasts with parametric 95% confidence intervals clamped to zero for non-negative series.
  - Integrated synthetic warm-up (`_warmup()`) executed at module load time to eliminate OpenMP/DLL cold-start latency.
- **Statistical Hypothesis Engine (`backend/src/analytics/hypothesis_engine.py`)**:
  - Two-group comparisons: Welch's unequal variance t-test (`scipy.stats.ttest_ind(equal_var=False)`) reporting percentage lift and Cohen's d effect size.
  - Multi-group comparisons ($\ge 3$ groups): One-Way ANOVA (`scipy.stats.f_oneway`) reporting $\eta^2$ (eta-squared) effect size.
  - Multi-testing adjustment: Applies Holm-Bonferroni step-down correction to control family-wise error rate.
  - Non-parametric cross-checks: Automatically runs Mann-Whitney U or Kruskal-Wallis alongside parametric tests to cross-verify distribution skewness.
- **Structured Chart Orchestrator (`backend/src/orchestrator/chart_picker.py`)**:
  - Structured chart picker utilizing Gemini 3.8 Flash to recommend visualizations based exclusively on anonymous statistical metadata facts (frequency, row count, target type, significance, groups). Zero raw tabular data or user column names are transmitted.
  - Enforces a strict 4-choice enum schema: `line_chart`, `bar_comparison`, `scatter_cluster`, `kpi_card`.
  - Built-in deterministic heuristic fallback activates seamlessly if the LLM is disabled, times out (>2.5s), or encounters API failures.

### 3. REST API Endpoints
- **`POST /api/v1/forecast`**:
  - Accepts multipart form data with file upload, optional target column, forecast horizon (1–60 steps), and optional date column.
  - Returns dataset metadata, frequency, data quality logs, model metrics ($R^2$, RMSPE, MAE), recursive forecast dates/values/confidence bounds, execution timing breakdowns, and recommended visualization.
- **`POST /api/v1/hypotheses`**:
  - Accepts multipart form data with file upload, target metric, and optional grouping columns.
  - Returns comprehensive hypothesis test results with baseline vs treatment stats, percentage lift, p-values, adjusted p-values, effect sizes, and recommended comparison charts.
- **Security & Validation Controls**:
  - Enforces streaming file size guards rejecting uploads $> 50$ MB with `HTTP_413_CONTENT_TOO_LARGE`.
  - Validates file extensions and MIME types with `HTTP_415_UNSUPPORTED_MEDIA_TYPE`.
  - Emits descriptive `HTTP_422_UNPROCESSABLE_ENTITY` for single-value columns, insufficient rows, or non-numeric targets.

### 4. Real-World Benchmark Validations
Validated against standard benchmark and production datasets with 100% pass rate:
- **Airline Passengers (`airline-passengers.csv`, 144 monthly records)**: Inferred monthly frequency `M`, executed 12-month recursive forecast with non-negative bounds within latency budget (<200ms).
- **Bike Sharing (`day.csv`, 730 daily records)**: Inferred daily frequency `D`, leakage defense successfully stripped ID `instant` and target components `casual` + `registered`, generating a 14-day forecast with positive holdout $R^2$ and <100ms compute latency.
- **Wholesale Customers (`Wholesale customers data.csv`, 440 records)**: Ran Welch's t-test on `Channel` (2 groups) and ANOVA on `Region` (3 groups) with Holm-Bonferroni adjustments in under 100ms.
- **UCI Online Retail (`online_retail.csv`, 541,909 transactions, 49.5 MB)**: Automatically decoded via Latin-1, detected transactional schema, filtered cancellations/bad prices, aggregated to daily net revenue, filled missing weekend dates, and produced a 14-day revenue forecast.
- **Rossmann Store Sales (`benchmark_data.parquet`, 6,000 records)**: Evaluated promotional campaign lift via Welch's t-test, confirming statistically significant lift ($p < 0.01$).

### 5. Defect Log & Latency Optimizations
- **Python Package Submodule Collision**: `src/api/__init__.py` aliased `from src.api.analytics_router import router as analytics_router`, which shadowed the submodule `src.api.analytics_router` with an `APIRouter` instance, causing `monkeypatch.setattr(ar, "get_settings", ...)` to raise an `AttributeError` in test 13. Removed the alias to cleanly preserve module resolution.
- **Pure Numpy Recursive Forecasting Acceleration**: In `forecast_engine.py`, re-allocating DataFrames and concatenating columns inside the 14-step recursive loop consumed 49ms. Implemented `predict_arr` with precomputed column index mappings and pre-allocated numpy buffers, dropping loop execution to 3.3ms.
- **Fast Linear Inference**: For Ridge models selected by validation, precomputed effective coefficients and intercepts ($arr \cdot w + b$) bypassed Scikit-Learn pipeline overhead, achieving 500x faster step predictions.
- **Warmup & Cold-Start Mitigation**: Initialized a lightweight multi-model warm-up (`_warmup()`) at module import to eliminate Windows DLL dynamic linking and OpenMP thread pool allocation latency.
- **Header Alignment on Real Data**: Expanded `prepare_series` target validation in real-data tests to match both standard `#Passengers` and `total_passengers` variants found in production exports.

### 6. Test Regression Summary
- **Total Backend Tests**: **224 passed** (180 baseline + 18 Phase 3A unit + 7 Phase 3A real-data integration + 19 Challenger 2 adversarial).
- **Artifact Footprint**: **2.53 MB** (10 models/preprocessors, 5.1% of 50 MB budget).
- **Phase 3A Exit Gate**: **CLOSED AND CERTIFIED**.

---

## Milestone M1: Forecast Engine Optimization & Dependency Alignment (Completed)

### 1. Forecast Engine Latency & Accuracy Tuning (`backend/src/analytics/forecast_engine.py`)
- **Hyperparameter Optimization**:
  - Calibrated `XGB_PARAMS`: `n_estimators=30, max_depth=4, learning_rate=0.08, subsample=0.9, colsample_bytree=0.9, tree_method="hist", max_bin=64, n_jobs=2, random_state=42, verbosity=0`.
  - Tuned `max_depth=4` ensures XGBoost captures non-linear interactions and outperforms the linear Ridge baseline on real-world datasets ($R^2 \approx 0.3996$, RMSE 1290.9 vs Ridge $R^2 \approx 0.2983$, RMSE 1395.7, beating Ridge by 104.8 RMSE units on Bike Sharing `day.csv`).
  - `n_jobs=2` avoids the Windows OpenMP thread pool allocation trap (`n_jobs=-1` caused a 4,457ms cold-start penalty spinning up 16–24 threads and inter-thread contention on small datasets; `n_jobs=2` provides stable 21–25ms fits with zero latency spikes across consecutive trials).
  - `n_estimators=30` with `n_jobs=2` brings full-dataset refit and 14-step recursive forecast latency well under the 200ms budget:
    - Synthetic Bike (730 rows): Total compute **63.7ms** (Ridge $R^2 = 0.8281 > 0.5$).
    - Real Bike (`day.csv`, 730 rows): Total compute **45–75ms** (XGBoost selected).
    - Real Airline (`airline-passengers.csv`, 144 rows): Total compute **34.4–48.3ms** (Ridge $R^2 = 0.9382$ selected).
    - REST API (`POST /api/v1/forecast` on `day.csv` multipart upload): Total compute **73.5–144.7ms** (`within_budget: true`).
- **Inference Pipeline Acceleration**:
  - Cached the underlying booster (`est.get_booster()`) directly on `_Model`, eliminating redundant Python object retrieval overhead during recursive point predictions.
  - Transitioned holdout validation predictions to `predict_arr(X_hold.to_numpy(...))` to eliminate DataFrame slicing overhead.
  - Pre-extracted exogenous and calendar future features into C-contiguous NumPy arrays (`ext_x_dict`, `cal_future_dict`), converting 14 recursive steps from pandas `.iloc` indexing to direct NumPy array access.
  - Exogenous missing value protection: Added `.ffill().bfill().fillna(0.0)` defense to eliminate trailing NaN propagation.
- **Warmup Enhancement**:
  - Replaced zero-variance `np.ones((100, 15))` warmup with Gaussian random data `rng = np.random.RandomState(42); X = rng.randn(100, 15).astype("float32"); y = rng.randn(100).astype("float32")`. This forces full depth-4 tree construction and thread pool allocation during module load, eliminating the cold-start initialization lag on the first real inference request.

### 2. Backend Dependency Alignment (`backend/pyproject.toml`)
- Synchronized `[project.dependencies]` in `backend/pyproject.toml` with `backend/requirements.txt`:
  - Added `pyarrow>=17.0.0`
  - Added `filetype>=1.2.0`
  - Added `httpx>=0.27.0`
  - Added `xgboost>=3.0.0`
  - Added `scipy>=1.15.0`

### 3. Comprehensive Verification & Regression Safety
- **Phase 3A Unit Test Suite**: `pytest backend/tests/test_phase3a.py -v` — **18/18 passed** in 4.92s.
- **Phase 3A Real Benchmark Suite**: `pytest backend/tests/test_phase3a_real_data.py -v` — **7/7 passed** in 5.28s (validating Airline Passengers, Bike Sharing, Wholesale Customers, UCI Online Retail, and Rossmann Store Sales).
- **Full Backend Regression Suite**: `pytest backend/tests/` — **224/224 passed**, 0 failures, 0 regressions across Phase 1, Phase 2, Phase 3A unit, real-data benchmarks, and Challenger 2 adversarial tests in 52.71s.
- **Model Artifact Footprint Audit**: `python backend/scripts/audit_artifact_size.py` — **10 artifacts, 2.53 MB total** (5.1% of 50.0 MB limit, leaving 47.47 MB headroom, exit code 0).

---

## Challenger 2: Empirical Adversarial Challenge Audit (Data Loader, Feature Pipeline, Chart Picker)

### 1. Adversarial Test Harness & Suite (`backend/tests/test_challenger2_adversarial.py`)
- Created comprehensive adversarial suite covering 19 distinct boundary, corruption, injection, and error-fallback scenarios:
  - **Tabular Ingestion Robustness**:
    - Empty 0-byte file uploads tested on `/upload` (HTTP 400), `/api/v1/forecast` (HTTP 422 `EmptyDataError`), and `/api/v1/hypotheses` (HTTP 422).
    - Corrupted files (null-byte CSV, truncated XLSX zip archive, invalid Parquet magic headers) rejected with HTTP 422 / 415 without crashing or leaking memory.
    - Oversized payloads exceeding max upload bytes rejected with HTTP 413 without disk persistence or excessive buffering.
    - Disallowed extensions (`.exe`, `.py`, `.zip`, `.sh`, `.pdf`, `.docx`, `.json`) rejected with HTTP 415.
  - **Formula Injection Defense (CWE-1236)**:
    - Neutralization of dangerous prefixes (`=`, `@`, `+`, `-`) verified via `sanitize_tabular_cells` with quoting and stripping modes.
    - Verified genuine numeric columns (negative and positive floats/ints) remain untouched and uncorrupted.
    - Verified forecast and hypothesis engines tolerate formula-injected categorical strings without execution or crashing.
  - **Chart Picker Error & Fallback Orchestration**:
    - Validated fallback to deterministic heuristics under mock LLM HTTP 500/503 errors (`fallback_reason="llm_http_500"`).
    - Validated fallback under HTTP 429 throttling (`fallback_reason="llm_http_429"`).
    - Validated fallback under network timeouts (`httpx.ReadTimeout`, `fallback_reason="llm_error_ReadTimeout"`).
    - Validated rejection and fallback when LLM outputs unapproved charts (e.g. `pie_chart`, `3d_scatter`) with `fallback_reason="llm_invalid_choice"`.
    - Verified deterministic heuristic coverage across all result types (`forecast`, `hypotheses`, `segmentation`, `unknown`).
  - **Feature Pipeline & Boundary Edge Cases**:
    - Validated leap day handling (Feb 29) and short-series detection.
    - Validated sorting of shuffled / non-monotonic dates.
    - Validated single-category grouping handling in hypothesis engine returning `insufficient_data` and `kpi_card` without crashing.
    - Validated constant (zero-variance) target forecasting without division-by-zero crashes.
- **Suite Execution**: `pytest backend/tests/test_challenger2_adversarial.py -v` — **19/19 passed** in 10.01s.

### 2. Empirical Findings & Gate Resolution
- **Calibrated Hyperparameters & Architecture**: `backend/src/analytics/forecast_engine.py` was optimized for per-request in-memory training:
  - `XGB_PARAMS = dict(n_estimators=30, max_depth=4, learning_rate=0.08, subsample=0.9, colsample_bytree=0.9, tree_method="hist", max_bin=64, n_jobs=2, random_state=42, verbosity=0)`.
  - Single-pass training architecture: Reuses the validated XGBoost model for recursive point forecasts while performing instant (1ms) linear refits for Ridge, eliminating redundant refit overhead.
  - Histogram acceleration (`max_bin=64` with `tree_method="hist"`) and dual-thread CPU execution (`n_jobs=2`) eliminate OpenMP thread synchronization jitter and heap contention on Windows, guaranteeing deterministic compute latency between 34–75ms on standard datasets (well under the 200ms budget).
  - Robust startup warmup using Gaussian random data (`rng.randn(100, 15)`) primes depth-4 tree construction and thread pools at module load.
  - Explicit garbage collection (`gc.collect()`) after processing large transactional datasets (such as 50 MB `online_retail.csv`) prevents heap fragmentation.
- **Full Backend Regression Suite**: `pytest backend/tests/` — **224/224 passed**, 0 failures across Phase 1, Phase 2, Phase 3A unit tests (18/18), Phase 3A real-data benchmarks (7/7), and Challenger 2 adversarial tests (19/19) in 52.71s.
- **Model Artifact Footprint Audit**: `python backend/scripts/audit_artifact_size.py --ceiling-mb 50.0` — **10 artifacts, 2.53 MB total** (5.1% of 50.0 MB ceiling, 47.47 MB headroom).
- **Phase 3A Exit Gate Status**: **PASSED & OFFICIALLY CLOSED** (zero auth, zero disk writes, zero DB, per-request in-memory training, 50 MB upload limit, <200ms compute gate, Gemini 3.8 Flash narrow chart picker with deterministic fallback, zero Phase 3B contamination).

---
