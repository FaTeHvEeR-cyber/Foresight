# Phase 3A Analytics Specification Mining Report

**Date**: 2026-09-19T18:27:00Z  
**Author**: Spec Miner 1 (`d:\Foresight\.agents\spec_miner_1`)  
**Target Milestone**: Phase 3A Analytics (R1–R5)  
**Parent Conversation ID**: `9fc34338-58ae-4118-9020-3367910ed0e9`  

---

## Executive Summary

This specification mining report provides an exhaustive, authoritative breakdown of functional and non-functional requirements, mathematical formulations, API payload contracts, latency constraints, and governance invariants for Phase 3A Analytics in Foresight.

Key authoritative findings:
1. **Existing Baseline Safety**: Existing test suite passes **180/180** tests across ingestion, sanitization, security gate, and training pipelines.
2. **Phase 3A Suite Execution**: `pytest backend/tests/test_phase3a.py` executes 18 tests, yielding **17 PASSED, 1 FAILED**. The sole failure is `test_forecast_quality_and_latency_on_bike` where `res["timing_ms"]["compute_total"]` was **358.4ms** exceeding the `< 200ms` test threshold (and the `< 100ms` batch inference budget).
3. **Model Footprint Compliance**: Existing serialized models in `backend/models/` total **2.53 MB** (5.1% of the 50.0 MB ceiling, 47.47 MB headroom remaining).
4. **Dual Forecasting Architecture**: The codebase requires both **dynamic fast-fit forecasting** for raw arbitrary user tables, and **pre-trained lazy model loading** (`ModelRegistry`) for sub-100ms batch scoring.

---

## 1. Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | R1: Loader | In-Memory Tabular Loader | Decodes raw upload bytes in RAM via `io.BytesIO`; autodetects delimiters and tries UTF-8 then Latin-1. | `raw: bytes`, `filename: str` | `pd.DataFrame` | Raises `UnsupportedFormat` (HTTP 415) if format not supported; raises 422 if table unparseable. | `backend/src/analytics/loader.py:18-35` |
| 2 | R1: Pipeline | Automated Date Column & Dayfirst Detection | Finds date column via regex (`_ISO_RE`, `_DMY_RE`) or dtype; infers day-first vs month-first by parsing order smoothness. | `df: pd.DataFrame`, `hint: Optional[str]` | `(parsed_dates: pd.Series, format_label: str)` | Raises `NoDateColumn` (HTTP 422) if no date column detected. | `backend/src/analytics/feature_pipeline.py:62-123` |
| 3 | R1: Pipeline | Multi-Frequency Inference & Aggregation | Determines frequency (D, W, M, Q) via median day difference of unique dates; aggregates multiple rows per period (sum/mean). | `dates: DatetimeIndex`, target & exog columns | Period-indexed `pd.DataFrame` with regular frequency | Raises `SeriesTooShort` (HTTP 200 `insufficient_data`) if < 3 dates or irregular frequency. | `backend/src/analytics/feature_pipeline.py:125-138, 321-344` |
| 4 | R1: Pipeline | Target Leakage & Component Pruning | Discovers and prunes columns identical to target, near-duplicates ($\|r\| > 0.9999$), or exact pair-sums ($y = a + b$). | `df: pd.DataFrame`, `target: str`, `candidate_cols: list[str]` | `leaks: dict[str, str]` (pruned from features) | None (silent detection and logging in `preprocessing.dropped_columns`). | `backend/src/analytics/feature_pipeline.py:189-212` |
| 5 | R1: Pipeline | Retail Transaction Log Aggregator | Special handler for UCI Online Retail logs; filters cancellations (`C*`), invalid prices ($\le 0$), computes daily net revenue, fills non-trading days with 0. | `df: pd.DataFrame` matching `is_retail_transactions()` | `(daily_df, data_quality_dict, fmt, date_col)` | Falls back to generic series preparation if not retail transaction format. | `backend/src/analytics/feature_pipeline.py:229-263` |
| 6 | R1: Pipeline | Leakage-Safe Calendar & Temporal Features | Generates cyclical sin/cos features for month/dow, lags $y_{t-l}$, rolling window stats (mean, std, min, max) on shifted past target ($y_{t-\min(\text{lags})}$). | `y: pd.Series`, `exog: pd.DataFrame`, `cfg: FreqConfig`, `lags: list`, `windows: list` | Feature `pd.DataFrame` | Guarantees $y_t$ never affects row $t$ features. | `backend/src/analytics/feature_pipeline.py:352-405` |
| 7 | R1: Pipeline | Out-of-Fold Expanding Mean Encoding | Encodes categorical features (DOW, month) into running target mean with smoothing parameter $m=10.0$; excludes current row target. | `y: np.ndarray`, `cat: np.ndarray`, `m: float = 10.0` | `encoded: np.ndarray`, train lookup dict | Unseen categories map to global running target mean. | `backend/src/analytics/feature_pipeline.py:410-436` |
| 8 | R2: Forecast | Dynamic In-Memory Model Fitting | Fits Ridge baseline and XGBoost primary on chronological train split, selects winner by validation RMSE, refits on full series. | `prep: PreparedSeries`, `horizon: Optional[int]` | Forecast result dict with point predictions, approximate 95% CI, and metrics | Raises `SeriesTooShort` if series cannot support minimum lags. | `backend/src/analytics/forecast_engine.py:83-181` |
| 9 | R2: Forecast | Pre-Trained Model Lazy Loader | Singleton caching registry (`ModelRegistry`) deserializing `.joblib` models on first request for sub-100ms batch scoring. | `artifact_name: str` | Deserialized model / pipeline / scaler instance | Raises `FileNotFoundError` if artifact missing. | `SKILL.md:43-52`, `AGENTS.md §5` |
| 10 | R2: Forecast | Target Log-Transform & Non-Negative Clamping | Trains XGBoost on $\log(1+y)$ for non-negative targets; inverts predictions via $\exp(p)-1$ and clips at 0.0. | `y: np.ndarray`, `log_target: bool`, `nonneg: bool` | Model predictions in original scale $\ge 0.0$ | None. | `backend/src/analytics/forecast_engine.py:45-61` |
| 11 | R2: Hypotheses | Welch's t-test Engine | Evaluates 2-group comparisons with unequal variances via `scipy.stats.ttest_ind(equal_var=False)`, computes lift %, Cohen's d. | `df: pd.DataFrame`, `target: str`, `group_cols: list[str]` | Test result dict: t-stat, p-value, df, lift %, Cohen's d, verdict | Skips columns with < 2 groups of $\ge 5$ samples or zero variance. | `backend/src/analytics/hypothesis_engine.py:78-88` |
| 12 | R2: Hypotheses | One-Way ANOVA Engine | Evaluates 3+ group comparisons via `scipy.stats.f_oneway`, computes $\eta^2$ effect size. | 3+ group arrays of target values | Test result dict: F-stat, p-value, df, $\eta^2$ | Skips degenerate variance. | `backend/src/analytics/hypothesis_engine.py:89-97` |
| 13 | R2: Hypotheses | Non-Parametric Validation & Skew Warnings | Evaluates Mann-Whitney U or Kruskal-Wallis on seeded sample ($\le 50,000$); flags skewness if $\|\text{skew}\| > 2$ and checks robustness. | Target arrays, RNG seed 42 | `nonparametric_p`, `robust: bool`, `skew_warning: bool` | Skew warning adds user note recommending non-parametric p-value. | `backend/src/analytics/hypothesis_engine.py:75-77, 114-118` |
| 14 | R2: Hypotheses | Holm-Bonferroni P-Value Adjustment | Adjusts raw p-values across multiple hypothesis tests to control family-wise error rate at $\alpha = 0.05$. | `pvals: list[float]` | `p_value_adjusted: list[float]`, `significant: bool` | None. | `backend/src/analytics/hypothesis_engine.py:16-25, 110-113` |
| 15 | R3: API | `POST /api/v1/forecast` Endpoint | Accepts multipart upload file + target/horizon form params; returns time series, actuals, forecast, holdout, metrics, recommended chart. | `file: UploadFile`, `target: str`, `date_col: str`, `horizon: int`, `use_llm: bool` | JSON response adhering to `ForecastResponse` contract | Returns HTTP 413 (>50MB), 415 (bad ext), 422 (unparseable table/target), or 200 with `insufficient_data`. | `backend/src/api/analytics_router.py:64-86` |
| 16 | R3: API | `POST /api/v1/hypotheses` Endpoint | Accepts multipart upload file + target/group_cols form params; returns statistical tests, lift %, p-values, group stats, recommended chart. | `file: UploadFile`, `target: str`, `group_cols: str`, `use_llm: bool` | JSON response adhering to `HypothesisResponse` contract | Returns HTTP 413 (>50MB), 415 (bad ext), 422 (target missing), or 200 with `insufficient_data`. | `backend/src/api/analytics_router.py:98-117` |
| 17 | R3: Orchestrator| Chart Picker Heuristic Fallback | Deterministic rule-based mapper: forecast $\to$ `line_chart`, hypotheses with tests $\to$ `bar_comparison`, segmentation $\to$ `scatter_cluster`, fallback $\to$ `kpi_card`. | `kind: str`, `facts: dict` | `(chart: str, reason: str)` | Guarantees an allowed chart is returned under any LLM failure. | `backend/src/orchestrator/chart_picker.py:29-42` |
| 18 | R3: Orchestrator| Chart Picker LLM Recommender | Async Gemini 3.8 Flash caller with structured JSON schema output (`chart`, `reason`); passes anonymous metadata only (no column names or data cells). | `kind: str`, `facts: dict`, `settings: Settings` | JSON dict with recommended `chart`, `reason`, `source="llm"`, `model` | Falls back to heuristic on timeout (2.5s), 429 throttled, invalid choice, or missing key. | `backend/src/orchestrator/chart_picker.py:44-83` |
| 19 | R5: Governance | Artifact Footprint Enforcement | Audits all `.joblib` model artifacts against the 50.0 MB ceiling; enforces `compress=3` serialization. | `models/` directory | Exit 0 if $\le 50.0$ MB; raises `AssertionError` with overage if breached | CLI exit code 1 / `AssertionError` on breach. | `backend/scripts/audit_artifact_size.py:87-199`, `AGENTS.md §2` |
| 20 | R5: Governance | Ephemeral Memory Lifecycle Guardrail | Context manager dereferencing intermediate DataFrames/buffers (`None`) and triggering `gc.collect()` in `finally` block; zero disk persistence. | Execution scope | Cleaned memory, dereferenced locals | Re-raises underlying business exceptions cleanly. | `backend/src/memory/lifecycle.py:93-235`, `AGENTS.md §1` |

---

## 2. Edge Cases Observed & Validated

| # | Feature | Input / Condition | Observed Behavior | Authoritative Reference |
|---|---------|-------------------|-------------------|------------------------|
| 1 | Date Parsing | UK / European DD-MM-YYYY format (e.g. `01-01-2018` in Bike Sharing) | Correctly identified as `day-first` via component comparison (`a > 12` vs `b > 12`); dates parsed without year/day inversion. | `test_phase3a.py:21-26` |
| 2 | Retail Transactions | Cancellations (InvoiceNo starts with `C`, Quantity $\le 0$) | 300 cancellation rows successfully dropped; data quality dictionary records `cancellation_rows_dropped = 300`. | `test_phase3a.py:43-50`, `feature_pipeline.py:248-251` |
| 3 | Retail Transactions | Zero/negative UnitPrice | Flagged and excluded from net revenue calculation; recorded in `zero_or_negative_price_rows_dropped`. | `feature_pipeline.py:252-254` |
| 4 | Retail Transactions | Non-trading days (Saturdays in UK retail) | Period reindexing detects missing trading days and fills target with `0.0` revenue (not linear interpolation). | `feature_pipeline.py:338-341` |
| 5 | Retail Transactions | Latin-1 Character Encoding (`CAFÉ MUG`) | File successfully loaded via `latin-1` fallback decoding when UTF-8 fails; returns HTTP 200. | `test_phase3a.py:110-115`, `loader.py:23-28` |
| 6 | Target Components | Exact sum target leakage (`cnt = casual + registered`) | Target component detector isolates `casual` and `registered`, drops them from exogenous features, logs reason. | `test_phase3a.py:28-33`, `feature_pipeline.py:205-211` |
| 7 | Short Time Series | Series length = 15 periods (fewer than needed for lags + holdout + 20) | Returns HTTP 200 with `status="insufficient_data"` and descriptive message `"Upload a longer history"` (does not crash with 500 or 422). | `test_phase3a.py:52-56`, `feature_pipeline.py:364-367` |
| 8 | Feature Leakage | Altering target value of final row ($y_N = 10^9$) | Feature values at row $N$ ($F_1[N] == F_2[N]$) remain completely unchanged, proving strictly zero forward target leakage. | `test_phase3a.py:66-73` |
| 9 | Mean Encoding | Altering target value of final row ($y_N = 9999$) | Expanding encodings for all prior rows ($0 \dots N-1$) remain identical, proving out-of-fold temporal protection. | `test_phase3a.py:58-64` |
| 10 | Target Skewness | Highly skewed target distributions ($\| \text{skew} \| > 2$) | Hypothesis engine outputs `skew_warning = True` and appends note prompting comparison against non-parametric p-values. | `test_phase3a.py:92-98`, `hypothesis_engine.py:103, 117-118` |
| 11 | Low Variance Groups | Group with zero variance or identical target values | Hypothesis engine skips degenerate group, logs skipped reason (`"no variance in the target within groups"`). | `hypothesis_engine.py:70-72` |
| 12 | File Size Limit | Upload exceeding 50MB (e.g. 50MB + 1024 bytes) | Rejected with HTTP 413 `Content Too Large` (or HTTP 400 in Phase 2 `/upload` gatekeeper). | `test_phase3a.py:117-124`, `analytics_router.py:29-33` |
| 13 | Bad File Format | Disallowed extension (`a.bin`) sent to `/api/v1/forecast` | Rejected with HTTP 415 `Unsupported Media Type` by `_load()`. | `test_phase3a.py:123`, `analytics_router.py:36-43` |
| 14 | LLM Throttled / 429 | Gemini API returns HTTP 429 | Chart picker catches non-200 status, gracefully falls back to heuristic choice with `fallback_reason = "llm_http_429"`. | `test_phase3a.py:155-161`, `chart_picker.py:69-70` |
| 15 | LLM Invalid Choice | Gemini API returns hallucinated chart type (`pie_3d`) | Chart picker validates against `ALLOWED`, rejects invalid chart, falls back to heuristic with `fallback_reason = "llm_invalid_choice"`. | `test_phase3a.py:156`, `chart_picker.py:77-78` |
| 16 | Missing API Key | `google_api_key = ""` | Chart picker immediately selects heuristic choice with `fallback_reason = "no_api_key"` in $< 1$ ms without external network request. | `test_phase3a.py:163-167`, `chart_picker.py:53-54` |
| 17 | Dynamic Forecast Latency | Dynamic training (XGBoost 100 trees + Ridge + refit + 14-step recursive loop) | Observed latency: **358.4ms** on CPU. Exceeds test threshold of 200ms and inference budget of 100ms. | `test_phase3a.py:82` execution log |

---

## 3. Comprehensive Requirements Specification (R1–R5)

### Requirement R1: Feature Pipeline & Data Loader

#### Supported Datasets & Canonical Schemas
1. **Bike Sharing**:
   - Primary Target: `cnt` (Total rental count).
   - Pruned ID: `instant`.
   - Pruned Components: `casual`, `registered` (because $\text{cnt} = \text{casual} + \text{registered}$).
   - Date Column: `dteday` (format `dd-mm-yyyy`, requires `day-first` inference).
   - Frequency: Daily (`"D"`).
   - Categoricals: `season`, `holiday`, `weekday`, `weathersit`.
   - Exogenous Numeric: `temp`, `atemp`, `hum`, `windspeed`.
2. **Online Retail**:
   - Source Format: Transaction log containing `InvoiceNo`, `StockCode`, `Description`, `Quantity`, `InvoiceDate`, `UnitPrice`.
   - Encoding: Must support `latin-1` (UCI dataset encoding) and `utf-8`.
   - Target Formulation: Derived daily `net_revenue = sum(Quantity * UnitPrice)`.
   - Data Cleansing Rules:
     - Exclude cancellations: `InvoiceNo` starts with `"C"` and `Quantity <= 0`.
     - Exclude bad prices: `UnitPrice <= 0`.
     - Retain returns: Negative quantities without `"C"` retained to net against revenue.
     - Non-trading gap handling: Retailers don't trade on Saturdays. Missing dates in `period_range` filled with `0.0` net revenue (not interpolated).
3. **Wholesale Customers**:
   - Structure: Tabular dataset with grouping dimensions `Channel` (1, 2) and `Region` (1, 2, 3) and annual spending features (`Fresh`, `Milk`, `Grocery`, `Frozen`, `Detergents_Paper`, `Delicassen`).
   - Primary Purpose: Hypothesis evaluation (`Channel` for 2-group Welch's t-test, `Region` for 3-group ANOVA) and clustering.
4. **Airline Passengers**:
   - Structure: Monthly international airline passenger numbers (144 periods, `1949-01` to `1960-12`).
   - Target: `#Passengers`.
   - Date Column: `Month` (format `%Y-%m`).
   - Frequency: Inferred as Monthly (`"M"`).
   - Lag Policy: Must NOT assign daily lags (7, 14, 21, 28). Must assign monthly lags `(1, 2, 3, 6, 12)` and rolling windows `(3, 6)`.
5. **Rossmann Store Sales**:
   - Structure: Multi-store daily time series (`store_id`, `date`, `units_sold`, `promo_flag`, etc.).
   - Evaluation Standard: RMSPE evaluated on rows where `units_sold >= 50` to avoid division-by-near-zero distortion.
   - Validation Split: Strict chronological holdout (last 6 weeks / 42 days), never random split.

#### Frequency Configuration Matrix
| Freq Label | Period Alias | Name | Lags | Rolling Windows | Seasonal Period | Holdout Periods | Default Horizon | Max Horizon |
|------------|--------------|------|------|-----------------|-----------------|-----------------|-----------------|-------------|
| `D` | `D` | daily | `(1, 7, 14, 21, 28)` | `(7, 30)` | 7 | 42 | 14 | 90 |
| `W` | `W` | weekly | `(1, 2, 4, 8, 52)` | `(4, 12)` | 52 | 8 | 8 | 26 |
| `M` | `M` | monthly | `(1, 2, 3, 6, 12)` | `(3, 6)` | 12 | 12 | 12 | 24 |
| `Q` | `Q` | quarterly | `(1, 2, 4)` | `(2, 4)` | 4 | 4 | 4 | 8 |

Frequency inference criteria based on median day difference $\Delta_{\text{days}}$:
- $\Delta_{\text{days}} \le 1.5 \implies \text{"D"}$
- $6 \le \Delta_{\text{days}} \le 8 \implies \text{"W"}$
- $27 \le \Delta_{\text{days}} \le 32 \implies \text{"M"}$
- $88 \le \Delta_{\text{days}} \le 93 \implies \text{"Q"}$
- Otherwise $\implies \text{None}$ (raises `SeriesTooShort`).

#### Leakage-Safe Feature Mathematics
1. **Calendar Encodings**:
   $$\text{cyc}_{\sin}(v, P) = \sin\left(\frac{2\pi v}{P}\right), \quad \text{cyc}_{\cos}(v, P) = \cos\left(\frac{2\pi v}{P}\right)$$
   Applied to Month ($P=12$) and Day of Week ($P=7$). Includes integer features `month`, `quarter`, `dow`, `dom`, `weekofyear`, `is_weekend`.
2. **Lag Features**:
   $$\text{lag}_l(t) = y(t - l) \quad \text{where } l \in \text{lags}, \, l \ge \min(\text{lags})$$
3. **Rolling Window Features**:
   $$\text{roll}_w(t) = \text{stat}\left(\{ y(t - \min(\text{lags}) - k) \}_{k=0}^{w-1}\right)$$
   Computes mean, std, min, max over window $w$. Because the base is shifted by $\min(\text{lags})$, observation $y(t)$ is never included.
4. **Exogenous Features**:
   $$x_{\text{feat}}(t) = x(t - 1)$$
5. **Smoothed Expanding Mean Encoding**:
   $$\hat{\mu}_i(c) = \frac{\sum_{k < i, \, \text{cat}_k = c} y_k + m \cdot \bar{y}_{<i}}{N_{<i}(c) + m}, \quad m = 10.0$$
   For training rows, computed cumulatively up to row $i-1$. For validation/inference, static mapping fitted on full training fold is applied.

---

### Requirement R2: Forecasting & Hypothesis Engines

#### 1. Forecasting Engine Specifications
- **Model Hierarchy**:
  1. `xgboost` (Primary): `XGBRegressor` capped at `max_depth <= 7` (production: 3 or 4), `tree_method="hist"`, `learning_rate=0.05-0.1`, `n_estimators=100` (or 30–50 for dynamic fast-fit).
  2. `ridge` (Baseline): `Ridge(alpha=1.0)` with `StandardScaler()`.
  3. `mlp` (Benchmark): `MLPRegressor(hidden_layer_sizes=(64, 32), learning_rate_init=0.001, early_stopping=True)`.
- **Target Transformation Invariant**:
  - If $y_{\min} \ge 0$, XGBoost is trained on $\log(1 + y)$ (`np.log1p`). Predictions inverted via $\exp(p) - 1$ (`np.expm1`) and clamped at 0.0. Ridge and MLP trained on raw target.
- **Latency Budget Contract**:
  - Batch inference target: **$< 100$ ms**.
  - To achieve $< 100$ ms:
    - Pre-trained models: Deserialized lazily via `ModelRegistry` and cached in memory. Inference executes in $< 15$ ms.
    - Dynamic fitting: If dynamic training is executed on the request path, estimator count and recursive feature loops must be tightly bounded (e.g. $n_{\text{est}} \le 30-50$, vectorized future feature generation) to keep total runtime within budget.
- **Metric Gates**:
  - $\text{RMSPE} = \sqrt{\frac{1}{N} \sum_{y_i \ne 0} \left(\frac{y_i - \hat{y}_i}{y_i}\right)^2} \times 100\%$ (evaluated on $y \ge 50$). Hard gate: $\le 15.0\%$.
  - $R^2 \ge 0.85$.
  - $\text{RMSPE}_{\text{xgboost}} < \text{RMSPE}_{\text{ridge}}$.

#### 2. Hypothesis Engine Specifications
- **Welch's Two-Sample t-Test**:
  $$t = \frac{\bar{X}_1 - \bar{X}_2}{\sqrt{\frac{s_1^2}{N_1} + \frac{s_2^2}{N_2}}}, \quad \nu = \frac{\left(\frac{s_1^2}{N_1} + \frac{s_2^2}{N_2}\right)^2}{\frac{(s_1^2/N_1)^2}{N_1 - 1} + \frac{(s_2^2/N_2)^2}{N_2 - 1}}$$
  Implemented via `scipy.stats.ttest_ind(a, b, equal_var=False)`.
- **Reported Outputs**:
  - `statistic`: t-statistic
  - `p_value`: unadjusted p-value
  - `p_value_adjusted`: Holm-Bonferroni adjusted p-value
  - `lift_pct`: $\left(\frac{\bar{X}_2}{\bar{X}_1} - 1\right) \times 100\%$
  - `effect_size`: Cohen's $d = \frac{\bar{X}_2 - \bar{X}_1}{\sqrt{(s_1^2 + s_2^2)/2}}$
  - `nonparametric_p`: Mann-Whitney U test p-value
  - `significant`: `bool(p_value_adjusted < 0.05)`
  - `robust`: `bool((nonparametric_p < 0.05) == significant_unadjusted)`
  - `significance_verdict`: Human-readable statement (e.g. `"Statistically significant increase of +38.70% (p = 0.0001 < 0.05)"`).
- **One-Way ANOVA (3+ Groups)**:
  - `scipy.stats.f_oneway(*arrays)`, effect size $\eta^2 = \frac{\text{SS}_{\text{between}}}{\text{SS}_{\text{total}}}$, non-parametric Kruskal-Wallis check.
- **Multiple Testing Correction**:
  - Holm-Bonferroni step-down: $p_{\text{adj}(k)} = \max_{j \le k} \min(1.0, (m - j + 1) p_{(j)})$.

---

### Requirement R3: API Router & Chart Orchestrator

#### API Route Specifications

##### 1. `POST /api/v1/forecast`
- **Request (multipart/form-data)**:
  - `file`: `UploadFile` (Required) — tabular file.
  - `target`: `Optional[str]` — target column name. Auto-picked if omitted.
  - `date_col`: `Optional[str]` — date column name. Auto-detected if omitted.
  - `horizon`: `Optional[int]` — forecast steps. Default per frequency config.
  - `use_llm`: `bool` (Default `True`) — enables Gemini chart recommendation.
- **Response Schema (`200 OK`)**:
```json
{
  "status": "ok",
  "dataset": {
    "date_column": "dteday",
    "target": "cnt",
    "frequency": "daily",
    "date_format": "day-first",
    "n_periods": 730,
    "start": "2018-01-01",
    "end": "2019-12-31"
  },
  "series": {
    "dates": ["2018-01-01", "..."],
    "actuals": [985.0, "..."]
  },
  "holdout": {
    "dates": ["2019-11-20", "..."],
    "actuals": [4120.0, "..."],
    "predictions": {
      "ridge": [4050.2, "..."],
      "xgboost": [4110.5, "..."]
    }
  },
  "forecast": {
    "model": "xgboost",
    "horizon": 14,
    "dates": ["2020-01-01", "..."],
    "values": [4200.1, "..."],
    "lower": [3500.0, "..."],
    "upper": [4900.2, "..."],
    "interval_note": "Approximate 95% band (±1.96 × holdout RMSE), constant width."
  },
  "metrics": {
    "ridge": { "rmspe": 0.12, "mae": 320.5, "rmse": 410.2, "r2": 0.81, "n": 42, "n_zero_actuals_excluded_from_rmspe": 0 },
    "xgboost": { "rmspe": 0.08, "mae": 210.3, "rmse": 295.1, "r2": 0.89, "n": 42, "n_zero_actuals_excluded_from_rmspe": 0 }
  },
  "selected_model": "xgboost",
  "skill_vs_seasonal_naive": 0.4521,
  "features": {
    "lags": [1, 7, 14, 21, 28],
    "rolling_windows": [7, 30],
    "holdout_periods": 42,
    "n_features": 16,
    "exogenous_columns_lagged_1": ["temp", "hum", "windspeed"]
  },
  "preprocessing": {
    "dropped_columns": [
      { "name": "instant", "reason": "ID / row counter" },
      { "name": "casual", "reason": "'cnt' = 'casual' + 'registered' (target component)" },
      { "name": "registered", "reason": "'cnt' = 'casual' + 'registered' (target component)" }
    ],
    "categorical_candidates": ["season", "holiday", "weekday"],
    "data_quality": {},
    "notes": ["Date format inferred as day-first."]
  },
  "timing_ms": {
    "load_parse": 4.5,
    "prepare_series": 12.1,
    "features": 8.3,
    "validation_fit": 35.2,
    "refit_and_forecast": 28.6,
    "compute_total": 88.7,
    "budget": 200,
    "within_budget": true
  },
  "recommended_visualization": {
    "chart": "line_chart",
    "reason": "Time series with a forecast horizon.",
    "source": "heuristic",
    "allowed": ["line_chart", "bar_comparison", "scatter_cluster", "kpi_card"],
    "latency_ms": 0.1
  }
}
```

##### 2. `POST /api/v1/hypotheses`
- **Request (multipart/form-data)**:
  - `file`: `UploadFile` (Required) — tabular file.
  - `target`: `Optional[str]` — numeric dependent variable.
  - `group_cols`: `Optional[str]` — comma-separated list of grouping columns.
  - `use_llm`: `bool` (Default `True`).
- **Response Schema (`200 OK`)**:
```json
{
  "status": "ok",
  "target": "Sales",
  "message": null,
  "alpha": 0.05,
  "tests": [
    {
      "test": "welch_t",
      "grouping_column": "Promo",
      "target": "Sales",
      "n_groups": 2,
      "statistic": 18.452,
      "p_value": 0.000001,
      "p_value_adjusted": 0.000001,
      "df": 582.4,
      "baseline_group": "0",
      "comparison_group": "1",
      "mean_difference": 1935.2,
      "lift_pct": 38.7,
      "effect_size": { "name": "cohens_d", "value": 1.52 },
      "nonparametric_p": 0.000001,
      "significant": true,
      "significant_unadjusted": true,
      "robust": true,
      "group_stats": [
        { "group": "0", "n": 300, "mean": 5000.1, "std": 412.3 },
        { "group": "1", "n": 300, "mean": 6935.3, "std": 398.7 }
      ],
      "target_skew": 0.12,
      "skew_warning": false
    }
  ],
  "skipped": [],
  "notes": [],
  "timing_ms": { "compute_total": 14.2 },
  "recommended_visualization": {
    "chart": "bar_comparison",
    "reason": "Group means compared across categories.",
    "source": "heuristic",
    "allowed": ["line_chart", "bar_comparison", "scatter_cluster", "kpi_card"],
    "latency_ms": 0.1
  }
}
```

##### 3. Status Codes & Error Mapping
| Code | Condition | Returned Message |
|------|-----------|------------------|
| `200` | Successful execution or valid dataset with insufficient periods | `status: "ok"` or `status: "insufficient_data"` with explanatory message |
| `413` | Upload exceeds `max_upload_bytes` (50MB) | `"File exceeds the 50 MB limit."` |
| `415` | Non-tabular file format (e.g. `.bin`, `.exe`) | `"Unsupported tabular format: 'a.bin'"` |
| `422` | No date column detected / target not found / corrupt table | Clear validation message identifying missing entity |

#### Chart Picker Rules & Orchestration
1. **Allowed Visualizations**: Fixed set: `["line_chart", "bar_comparison", "scatter_cluster", "kpi_card"]`.
2. **Heuristic Dispatch Rules**:
   - `kind == "forecast"`: `status == "ok"` $\to$ `"line_chart"`, else $\to$ `"kpi_card"`.
   - `kind == "hypotheses"`: `n_tests > 0` $\to$ `"bar_comparison"`, else $\to$ `"kpi_card"`.
   - `kind == "segmentation"`: `status == "ok"` $\to$ `"scatter_cluster"`, else $\to$ `"kpi_card"`.
   - Default $\to$ `"kpi_card"`.
3. **LLM Privacy Invariant**: Zero raw data leakage. Gemini prompt receives only anonymous aggregate facts: `{"result_type": "forecast", "status": "ok", "frequency": "daily", "n_periods": 730, "horizon": 14}`. No column names, row indices, or values leave the server.
4. **Fallback Handling**:
   - `llm_disabled`: `chart_picker_enabled=False` or `use_llm=False`.
   - `no_api_key`: `google_api_key` empty.
   - `llm_http_429`: HTTP 429 rate limit exceeded.
   - `llm_invalid_choice`: LLM outputs choice outside `ALLOWED`.
   - `llm_error_{Exception}`: Timeout ($> 2.5$s) or transport error.

---

### Requirement R4: Test Coverage & Regression Invariants
1. **Phase 3A Test Module**: `backend/tests/test_phase3a.py` with 18 test cases validating:
   - Date formats (day-first vs month-first).
   - Pruning target leakage (`instant`, `casual`, `registered`).
   - Monthly frequency without day lags (`Airline Passengers`).
   - Retail transaction log aggregation, cancellations, price filters, Saturday gap zero-fill.
   - Leakage-safe expanding encoding and temporal independence.
   - Welch's t-test on promotional lift (~38.7% lift).
   - Wholesale customers multi-group ANOVA and Welch's t-test.
   - API endpoints (`/api/v1/forecast`, `/api/v1/hypotheses`), status codes (413, 415, 422, 200).
   - Chart picker LLM integration, mocks, and all fallback modes.
2. **Regression Zero-Tolerance Guardrail**:
   - Running `pytest backend/tests/ -k "not test_phase3a"` must pass **180/180** tests across:
     - `test_ingestion.py`, `test_sanitization.py`, `test_validator.py`, `test_security_gate.py`.
     - `test_tabular_parser.py`, `test_document_parser.py`, `test_imputation.py`, `test_missing_values.py`.
     - `test_memory_lifecycle.py`, `test_rate_limit.py`, `test_oversized.py`.
     - `test_phase2_exit_criteria.py`, `test_train_engine_a.py`, `test_train_engine_b_anomaly.py`, `test_train_engine_b_clustering.py`, `test_audit_artifact_size.py`.

---

### Requirement R5: Governance, Footprint, and Documentation
1. **Model Footprint Ceiling (§5.2)**:
   - Combined size of all `.joblib` artifacts in `models/` or `backend/models/` must remain strictly **$< 50.0$ MB**.
   - Verified current size: **2.53 MB** (10 artifacts).
   - Compression rule: Mandatory `joblib.dump(..., compress=3)`.
   - XGBoost constraints: `max_depth <= 7`, early stopping enabled.
   - Verification tool: `python backend/scripts/audit_artifact_size.py --ceiling-mb 50.0`.
2. **Ephemeral Memory Lifecycle**:
   - Mandatory wrapping of all upload and processing routines with `ephemeral_processing()` context manager.
   - Intermediate DataFrames, raw bytes, and parser objects must be dereferenced to `None` and `gc.collect()` executed in `finally`.
   - Streaming in-memory decoding via `io.BytesIO`. Zero persistence of unvalidated raw datasets to disk.
3. **Continuous Documentation Invariant**:
   - `README.md` at the project root must be continuously updated upon task completion, logging architectural decisions, endpoint signatures, tuning parameters, and verification outputs.

---

## 4. Five-Component Handoff Report

### 1. Observation
- **Direct File Inspections**:
  - `backend/src/analytics/feature_pipeline.py` (lines 1–436): Implements complete frequency configs (`FREQ_CONFIGS`), date parsing (`infer_dayfirst`), leakage pruner (`detect_target_components`), retail log aggregator (`prepare_retail_daily`), calendar feature builder, and expanding mean encoder (`expanding_mean_encode`).
  - `backend/src/analytics/loader.py` (lines 18–35): In-memory bytes decoding supporting `.csv`, `.tsv`, `.txt` (UTF-8, Latin-1), `.xlsx`, `.parquet`.
  - `backend/src/analytics/forecast_engine.py` (lines 83–181): Implements `run_forecast()` executing Ridge + fast XGBoost fitting and recursive point forecasting with interval bounds.
  - `backend/src/analytics/hypothesis_engine.py` (lines 33–126): Implements `run_hypotheses()` executing Welch's t-test (`equal_var=False`), ANOVA, Mann-Whitney/Kruskal-Wallis cross-checks, and Holm-Bonferroni correction.
  - `backend/src/api/analytics_router.py` (lines 64–117): Mounts `POST /api/v1/forecast` and `POST /api/v1/hypotheses` wrapped in `ephemeral_processing()`.
  - `backend/src/orchestrator/chart_picker.py` (lines 29–83): Implements two-tier visualization picker (`line_chart`, `bar_comparison`, `scatter_cluster`, `kpi_card`) with deterministic heuristic and Gemini LLM.
- **Empirical Test Suite Execution Results**:
  - `pytest backend/tests/ -k "not test_phase3a"`: **180 passed**, 18 deselected in 40.64s. Zero regressions across existing Phase 2 suites.
  - `pytest backend/tests/test_phase3a.py`: **17 passed, 1 failed** in 8.13s.
    - Failure observed: `test_forecast_quality_and_latency_on_bike` failed on line 82:
      ```
      AssertionError: {'features': 19.1, 'validation_fit': 145.2, 'refit_and_forecast': 194.1, 'compute_total': 358.4}
      assert 358.4 < 200
      ```
  - `python backend/scripts/audit_artifact_size.py --ceiling-mb 50.0`: **PASSED**. Total size 2.53 MB (5.1% utilization of 50.0 MB ceiling, 47.47 MB headroom).

### 2. Logic Chain
1. *Observation*: `test_forecast_quality_and_latency_on_bike` failed because `compute_total = 358.4ms > 200ms`.
2. *Observation*: In `forecast_engine.py`, dynamic fitting trains XGBoost (100 trees) on validation split (145.2ms), then refits XGBoost on the full series and iterates a 14-step recursive forecast loop rebuilding features on every step (194.1ms).
3. *Observation*: Both `ORIGINAL_REQUEST.md` (line 17) and `AGENTS.md` (Section 5) require batch inference latency $< 100$ ms, and `model-inference-integration/SKILL.md` (lines 35-63) specifies lazy loading pre-trained models via `ModelRegistry`.
4. *Inference*: Dynamic training is computationally bounded by XGBoost tree construction on CPU. To achieve $< 200$ ms (or $< 100$ ms) for dynamic forecasting, tree count can be reduced (e.g., $n_{\text{est}} \le 30-50$) and future recursive feature computation vectorized. For pre-trained models, lazy loading via `ModelRegistry` allows instant inference ($< 15$ ms).
5. *Observation*: `backend/main.py` and `backend/app/main.py` already import and mount `analytics_router` (`app.include_router(analytics_router)`).
6. *Observation*: All 180 existing unit and integration tests pass without a single regression.
7. *Conclusion*: The Phase 3A codebase is structurally complete and 94.4% passing in tests. The primary operational gap is optimizing the dynamic forecasting latency in `forecast_engine.py` (or integrating `ModelRegistry` lazy loading) to bring execution time under budget.

### 3. Caveats
- **Hardware Variation**: Execution latency was benchmarked on local Windows CPU. Latency is sensitive to CPU load. Optimizing estimator count in dynamic fitting is critical for reliable pass rates across environments.
- **LLM Connectivity**: Live Gemini LLM calls in `chart_picker.py` require a valid `GOOGLE_API_KEY` in `.env`. When the key is missing, it cleanly falls back to heuristic choice (`fallback_reason = "no_api_key"`), as validated by test 18.
- **Dynamic Routing**: Dynamic UI schema and report chip routing is parked as a cosmetic placeholder per `AGENTS.md §1` and must not be coupled to backend logic.

### 4. Conclusion
All requirements R1–R5 are mined, formalized, and verified against authoritative code and tests:
- **R1** is fully satisfied by `feature_pipeline.py` and `loader.py` with multi-frequency handling, leakage-safe calendar/lag/rolling features, expanding mean encoding, and retail transaction aggregation.
- **R2** has mathematical rigor in `hypothesis_engine.py` (Welch's t-test with lift %, Holm correction, ANOVA, non-parametric checks) and `forecast_engine.py` (XGBoost + Ridge + log-transforms), needing only latency tuning in dynamic fitting to pass the $< 200$ ms / $< 100$ ms threshold.
- **R3** endpoints and schema contracts (`/api/v1/forecast`, `/api/v1/hypotheses`) and chart picker rules are verified and mapped.
- **R4** confirms 180/180 Phase 2 regression safety.
- **R5** confirms 2.53 MB / 50.0 MB footprint compliance and ephemeral memory governance.

### 5. Verification Method
To independently verify this specification report:
1. **Audit Artifact Footprint**:
   ```bash
   python backend/scripts/audit_artifact_size.py --ceiling-mb 50.0
   ```
   *Expected Output*: `[PASSED] Artifact footprint within architecture spec Section 5.2.` (Total ~2.53 MB).
2. **Verify Zero Regressions on Existing Suite**:
   ```bash
   pytest backend/tests/ -k "not test_phase3a"
   ```
   *Expected Output*: `180 passed`.
3. **Verify Phase 3A Analytics Suite**:
   ```bash
   pytest backend/tests/test_phase3a.py
   ```
   *Expected Output*: 17 passed, 1 failed (latency assertion on bike forecast).
4. **Inspect Code & Contracts**:
   - Inspect `backend/src/analytics/feature_pipeline.py`
   - Inspect `backend/src/analytics/forecast_engine.py`
   - Inspect `backend/src/analytics/hypothesis_engine.py`
   - Inspect `backend/src/api/analytics_router.py`
   - Inspect `backend/src/orchestrator/chart_picker.py`
