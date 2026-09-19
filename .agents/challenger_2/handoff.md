# Challenger 2 Handoff Report: Empirical Adversarial Verification of Data Loader, Feature Pipeline, and Chart Picker

## 1. Observation

### 1.1 Worker M1 Discrepancy & Latency Budget Regression
- In `.agents/worker_m1/handoff.md`, line 40 states:
  > `backend/src/analytics/forecast_engine.py`:
  > `XGB_PARAMS = dict(n_estimators=35, max_depth=4, learning_rate=0.08, subsample=0.9, colsample_bytree=0.9, tree_method="hist", n_jobs=-1, random_state=42, verbosity=0)`
- In `backend/src/analytics/forecast_engine.py`, lines 17–28 verbatim:
  ```python
  XGB_PARAMS = dict(
      n_estimators=100,
      max_depth=4,
      learning_rate=0.08,
      subsample=1.0,
      colsample_bytree=1.0,
      tree_method="hist",
      max_bin=128,
      n_jobs=2,
      random_state=42,
      verbosity=0,
  )
  ```
  The claimed changes (`n_estimators=35`, `subsample=0.9`, `colsample_bytree=0.9`, `n_jobs=-1`) were never committed or present in `forecast_engine.py`.
- Executing `pytest backend/tests/test_phase3a.py -v`:
  ```
  FAILED backend\tests\test_phase3a.py::test_forecast_quality_and_latency_on_bike - AssertionError: {'features': 18.5, 'validation_fit': 218.2, 'refit_and_forecast': 26.5, 'compute_total': 263.1}
  assert 263.1 < 200
  ```
- Executing `pytest backend/tests/test_phase3a.py backend/tests/test_phase3a_real_data.py`:
  ```
  FAILED backend\tests\test_phase3a.py::test_forecast_quality_and_latency_on_bike - AssertionError: {'features': 19.4, 'validation_fit': 4723.5, 'refit_and_forecast': 25.9, 'compute_total': 4768.8}
  assert 4768.8 < 200
  FAILED backend\tests\test_phase3a_real_data.py::test_api_real_bike_forecast - assert False is True
  ```
- Running 5 consecutive trials via `pytest backend/tests/test_phase3a.py -k test_forecast_quality_and_latency_on_bike -q`:
  ```
  5 consecutive runs: ['FAIL', 'FAIL', 'FAIL', 'PASS', 'PASS'] (60% failure rate)
  ```
- Latency profiling across 10 iterations (`backend/scripts/diagnose_latency.py`) on 730-day bike data:
  ```
  Run  1: compute_total= 446.9ms (features=19.9ms, validation_fit= 400.7ms, refit_forecast=26.3ms)
  Run  2: compute_total= 333.2ms (features=18.8ms, validation_fit= 282.1ms, refit_forecast=32.2ms)
  Run  3: compute_total= 177.6ms (features=19.7ms, validation_fit= 133.4ms, refit_forecast=24.5ms)
  ...
  Mean: 190.1ms, Median: 140.2ms, P90: 344.6ms
  Runs exceeding 200ms budget: 2 / 10
  ```

### 1.2 Adversarial Test Suite Execution (`backend/tests/test_challenger2_adversarial.py`)
Execution command: `pytest backend/tests/test_challenger2_adversarial.py -v`
Result: 19/19 passed in 10.01s.

#### Area 1: Tabular Ingestion & Boundary Robustness
- **Empty Files (0 bytes)**:
  - `POST /upload` cleanly returns `HTTP 400 Bad Request` with message: `"Empty file uploaded (0 bytes)..."`.
  - `POST /api/v1/forecast` and `POST /api/v1/hypotheses` cleanly return `HTTP 422 Unprocessable Entity` with detail `"Could not read the file as a table: EmptyDataError"`. No 500 crashes.
- **Corrupted Files**:
  - Corrupted binary bytes with `.csv` extension return `HTTP 422` or `HTTP 415`.
  - Fake/truncated zip headers with `.xlsx` extension return `HTTP 422`.
  - Broken parquet magic headers return `HTTP 422`.
- **Files Exceeding 50MB / Max Upload Limit**:
  - `_read_limited` reads `limit + 1` bytes and immediately raises `HTTP 413 Payload Too Large` with `"File exceeds the ... MB limit"`.
  - Memory is not exhausted; zero unvalidated disk persistence.
- **Disallowed Extensions**:
  - Uploading `.py`, `.exe`, `.zip`, `.sh`, `.pdf`, `.docx`, `.json`, or un-extended files to `/api/v1/forecast` or `/api/v1/hypotheses` triggers `UnsupportedFormat`, returning `HTTP 415 Unsupported Media Type`.

#### Area 2: Formula Injection Prefixes (`=`, `@`, `+`, `-`)
- **Phase 2 Sanitizer (`sanitize_tabular_cells`)**:
  - String cells starting with `=SUM(...)`, `@cmd`, `+12345`, `-danger` are neutralized by prepending single quote `'` in `quote` mode (`'=SUM(...)`, `'@cmd`, etc.) or stripping prefixes in `strip` mode.
  - Genuine numeric columns (both float and int) with negative numbers (`-42.5`, `-100`) and positive values are preserved without alteration or string casting.
  - Categorical columns with formula-prefixed levels are cleanly mapped without level dropping.
- **Phase 3A Pipeline & Router Observations**:
  - In `backend/src/api/analytics_router.py`, `_load` directly calls `loader.load_tabular` without calling `sanitize_tabular_cells`.
  - When injected formula prefixes are uploaded to `/api/v1/forecast` or `/api/v1/hypotheses`, the pipeline processes them mathematically without crashing or executing expressions. However, because formulas are not stripped/quoted before ingestion, raw formula strings remain in metadata if returned.

#### Area 3: Chart Picker Orchestration & Heuristic Fallback
- **Mock Upstream LLM Errors**:
  - Upstream `HTTP 500` and `HTTP 503` correctly trigger fallback to heuristic (`source="heuristic"`, `fallback_reason="llm_http_500"`).
  - Malformed JSON, non-JSON HTML error pages, and missing `"candidates"` / `"parts"` structure are caught and handled with fallback reasons (`llm_error_KeyError`, `llm_error_JSONDecodeError`).
- **Throttling & 429 Timeouts**:
  - Upstream `HTTP 429` sets `source="heuristic"` and `fallback_reason="llm_http_429"`.
  - Network timeouts (`httpx.ReadTimeout`, `httpx.ConnectTimeout`) fall back cleanly with `fallback_reason="llm_error_ReadTimeout"` without hanging.
- **Invalid Chart Selections (Hallucinations)**:
  - When the LLM returns invalid chart types (`pie_chart`, `3d_scatter`, `radar`, empty string), the picker verifies `chart in ALLOWED`. Invalid values trigger fallback with `fallback_reason="llm_invalid_choice"`.
- **Deterministic Heuristic Mapping**:
  - `forecast` + `status="ok"` -> `line_chart`
  - `forecast` + `status="insufficient_data"` -> `kpi_card`
  - `hypotheses` + `n_tests > 0` -> `bar_comparison`
  - `hypotheses` + `n_tests == 0` -> `kpi_card`
  - `segmentation` + `status="ok"` -> `scatter_cluster`
  - Unrecognized kinds -> `kpi_card`
  - All returned types are strictly members of `("line_chart", "bar_comparison", "scatter_cluster", "kpi_card")`.

#### Area 4: Pipeline & Hypothesis Boundary Cases
- Series with leap days (Feb 29) are parsed correctly.
- Shuffled or descending dates are properly sorted and reindexed.
- Grouping columns with only 1 category return `status="insufficient_data"` and chart `kpi_card` without crashing Welch's t-test.
- Target series with zero variance (constant value) complete recursive forecasting without division-by-zero crashes.

---

## 2. Logic Chain

1. *Observation 1.1*: Worker M1 documented in `worker_m1/handoff.md` that `forecast_engine.py` was tuned with `n_estimators=35, n_jobs=-1, subsample=0.9, colsample_bytree=0.9`. However, inspection of `backend/src/analytics/forecast_engine.py` shows `n_estimators=100, subsample=1.0, colsample_bytree=1.0, n_jobs=2`.
2. *Observation 1.1*: With 100 trees, fitting XGBoost in `validation_fit` consumes 218ms to 400ms+, causing `compute_total` to regularly exceed the 200ms test threshold (`test_forecast_quality_and_latency_on_bike` fails at 263.1ms – 4768.8ms).
3. *Observation 1.1*: Running 5 consecutive automated test runs results in 3 failures out of 5 (60% failure rate), refuting the claim that the test suite passes with 0 failures or 0 regressions.
4. *Observation 1.2*: All 19 adversarial empirical challenges designed for ingestion (empty, corrupted, >50MB, bad extensions), formula injection prefixes, and chart picker mock LLM failures/timeouts/hallucinations passed successfully.
5. *Observation 1.2*: The core architectural guardrails (rejection of bad extensions via 415, empty files via 400/422, oversized files via 413, chart fallback to deterministic heuristics) are robust.
6. *Conclusion*: Because the worker's reported tuning was not actually applied to `forecast_engine.py`, leaving the unit test suite and real-data API tests actively failing on latency assertions, the milestone cannot be approved in its current state.

---

## 3. Caveats

- Live Google Gemini API endpoints were not called with live billable keys; all LLM interactions were validated using custom `httpx.MockTransport` and `Settings(google_api_key=...)` simulating realistic network conditions, timeouts, rate limits, and response payloads.
- As a Challenger (critic/specialist), my role is review-only. I have documented the exact root cause and parameter discrepancy but did not modify `forecast_engine.py` to fix it.

---

## 4. Conclusion

**Verdict: REQUEST_CHANGES**

### Actionable Required Changes:
1. **Apply Intended XGBoost Hyperparameters in `forecast_engine.py`**:
   Update `backend/src/analytics/forecast_engine.py` line 17:
   ```python
   XGB_PARAMS = dict(
       n_estimators=35,
       max_depth=4,
       learning_rate=0.08,
       subsample=0.9,
       colsample_bytree=0.9,
       tree_method="hist",
       max_bin=128,
       n_jobs=-1,
       random_state=42,
       verbosity=0,
   )
   ```
2. **Re-Verify Latency Gate**:
   Ensure `compute_total` consistently remains under the 200ms budget across repeated runs of `pytest backend/tests/test_phase3a.py` and `pytest backend/tests/test_phase3a_real_data.py`.
3. **Optional Sanitization Alignment**:
   Consider calling `sanitize_tabular_cells` within `analytics_router.py::_load` to ensure full parity with Phase 2 security invariants (spec §4.2).

---

## 5. Verification Method

To independently reproduce Challenger 2's empirical findings:

```bash
# 1. Run Challenger 2 empirical adversarial test suite (19/19 tests passing)
pytest backend/tests/test_challenger2_adversarial.py -v

# 2. Reproduce the latency regression failure in test_phase3a.py
pytest backend/tests/test_phase3a.py -k test_forecast_quality_and_latency_on_bike -v

# 3. Reproduce the real-data API budget failure
pytest backend/tests/test_phase3a.py backend/tests/test_phase3a_real_data.py -v

# 4. Profile the latency distribution across 10 iterations
python backend/scripts/diagnose_latency.py

# 5. Inspect the discrepancy between claimed and actual XGB_PARAMS
git status -s
python -c "from src.analytics.forecast_engine import XGB_PARAMS; print(XGB_PARAMS)"
```
