# Handoff Report: Phase 3A Datasets, Ephemeral Ingestion, and Visualization Primitives

**Author**: Explorer Subagent (Survey 2)  
**Date**: 2026-09-19  
**Working Directory**: `d:\Foresight\.agents\explorer_survey_2`  
**Target Milestone**: Phase 3A Architecture, Data Loading, & Benchmark Survey  

---

## 1. Observation

### 1.1 Dataset and Benchmark Fixture Locations
- **Physical Datasets on Disk**:
  - `backend/data/benchmark_data.parquet` (90,934 bytes): 6,000 synthetic rows (50 stores × 120 days) generated via `backend/scripts/generate_benchmark_data.py`. Columns: `store_id`, `date`, `day_of_week`, `promo_flag`, `temperature`, `competitor_distance`, `store_type`, `region`, `inventory_level`, `customer_rating`, `local_holiday`, `units_sold`.
  - `backend/data/benchmark_data_ground_truth.parquet` (36,055 bytes): Ground truth anomaly labels `[row_index, is_anomaly]` (5% calibrated contamination rate).
  - No physical CSV or Parquet files exist on disk for the external benchmark datasets (Bike Sharing, Airline Passengers, Online Retail, Wholesale Customers, Rossmann Store Sales).
- **Serialized Model Artifacts**:
  - Located in `backend/models/` (and mirrored in root `models/`): 10 `.joblib` files totaling **2.53 MB** (5.1% of the 50.0 MB ceiling).
  - Validated by `python backend/scripts/audit_artifact_size.py`:
    ```text
    TOTAL COMBINED SIZE: 2.53 MB (2,653,912 bytes)
    BUDGET UTILIZATION:  5.1% of 50.0MB ceiling
    HEADROOM REMAINING:  47.47 MB (49,774,888 bytes)
    STATUS:              [PASSED] Artifact footprint within architecture spec Section 5.2.
    ```
- **Synthetic Test Fixtures in `backend/tests/conftest.py`**:
  - Lines 108–189 define session-scoped pandas DataFrame fixtures and byte serializers for the 5 benchmark datasets:
    1. `bike_df` (lines 109–127): 730 daily rows (2018-01-01 to 2019-12-31). Columns: `instant`, `dteday` (formatted `%d-%m-%Y`), `season`, `yr`, `mnth`, `holiday`, `weekday`, `temp`, `casual`, `registered`, `cnt`.
    2. `airline_df` (lines 130–135): 144 monthly rows (1949-01-01 to 1960-12-01). Columns: `Month` (`%Y-%m`), `#Passengers`.
    3. `retail_df` (lines 138–157): ~15,000 transaction rows across 321 trading days (Saturdays excluded). Columns: `index`, `InvoiceNo`, `StockCode`, `Description`, `Quantity`, `InvoiceDate` (`%m/%d/%Y %H:%M`), `UnitPrice`. Injects 300 cancellations (`InvoiceNo` prefixed with `"C"`, negative quantity) and 80 zero-price records.
    4. `wholesale_df` (lines 160–172): 440 cross-sectional rows. Columns: `Channel` (levels 1, 2), `Region` (levels 1, 2, 3), `Fresh`, `Milk`, `Grocery` (lognormal distributions).
    5. `promo_df` (lines 175–184): 600 daily rows. Columns: `Date` (`%Y-%m-%d`), `Sales` (with injected +38.7% promo effect), `Promo` (0 or 1).
    6. `to_csv_bytes(df, encoding="utf-8")` (lines 187–188): Encodes DataFrames to byte streams (including Latin-1 support).

### 1.2 Ephemeral Processing and Phase 2 Ingestion Lifecycle
- **Context Manager & Decorator**:
  - `backend/src/memory/lifecycle.py` implements `ephemeral_processing` (lines 93–235) and `EphemeralScope` (lines 52–91).
  - Scope management: `with ephemeral_processing() as scope:` allows explicit object registration (`scope.track(obj)`).
  - Frame-local cleanup: `_cleanup_frame_locals(frame)` inspects caller frame locals via `sys._getframe(1)` and sets intermediate objects (`pd.DataFrame`, `pd.Series`, `io.BytesIO`, `io.StringIO`, `bytearray`, `bytes > 1024`, `PdfReader`, `docx.document`) to `None`.
  - Guaranteed Garbage Collection: `finally: if self.force_gc: gc.collect()` guarantees memory collection even on unhandled exceptions.
- **In-Memory Tabular Parsing & Memory Optimization**:
  - `backend/src/parsers/tabular_parser.py`: `parse_tabular(file_bytes, extension)` reads bytes strictly from `io.BytesIO` without disk persistence.
  - Spec §5.2 Downcasting: `downcast_numeric_columns(df)` (lines 21–70) automatically converts `float64 -> float32` and `int64 -> int16/int32`.
  - Raw Null Profile: `compute_raw_null_profile(df)` (lines 193–230) computes null counts and percentages per column before any imputation occurs, maintaining strict separation between raw null data and modeling data.
- **Security Sanitization and Upload Guardrails**:
  - File Size Guardrail: `validate_file_size` (`backend/src/parsers/sanitization.py`: lines 207–254) rejects empty files (0 bytes -> HTTP 400) and files exceeding `settings.MAX_FILE_SIZE_MB` (HTTP 413). In `backend/src/api/analytics_router.py`, `_read_limited(file, limit)` enforces early streaming termination.
  - MIME and Extension Disagreement Defense: `validate_mime_and_extension` (`backend/src/parsers/sanitization.py`: lines 122–205) verifies the declared extension against `EXTENSION_TO_ALLOWED_MIMES` (lines 81–116). Disallowances or disagreements raise `MimeTypeError` (HTTP 415).
  - Formula Injection Neutralization (CWE-1236): `sanitize_tabular_cells` (`backend/src/parsers/sanitization.py`: lines 257–323) neutralizes formula prefixes (`=`, `@`, `+`, `-`) in string cells by prepending a single quote `'` or stripping the character.
  - Document & Tabular Separation: In `backend/main.py` and `backend/app/routers/ingestion.py`, file uploads are routed based on extension to tabular (`parse_tabular_file`) or document intelligence (`parse_document_file`), returning `UploadResponse`.

### 1.3 Chart Orchestrator and Dynamic Routing Architecture
- **Backend Chart Picker (`backend/src/orchestrator/chart_picker.py`)**:
  - Component Whitelist: `ALLOWED = ("line_chart", "bar_comparison", "scatter_cluster", "kpi_card")` (line 17).
  - LLM Prompting Boundary: Narrow Gemini 3.8 Flash call via `httpx.AsyncClient` sending only anonymous, aggregated statistics (`result_type`, `status`, `n_tests`, `frequency`, `n_periods`, `horizon`). Zero raw data cells or column names are passed.
  - Structured Output: Uses `generationConfig.responseSchema` with enum constraint matching `ALLOWED`.
  - Heuristic Fallback: `heuristic_pick(kind, facts)` (lines 29–42) triggers when LLM is disabled, API key is missing, or HTTP 429/timeout occurs:
    - `forecast`: `line_chart` (or `kpi_card` on error/insufficient data).
    - `hypotheses`: `bar_comparison` (or `kpi_card` when 0 tests).
    - `segmentation`: `scatter_cluster` (or `kpi_card` on error).
- **Dynamic Routing Guardrail (`frontend/components/query/ModeChips.tsx` & `frontend/types/schema.ts`)**:
  - `frontend/components/query/ModeChips.tsx` (lines 3–10) explicitly notes:
    ```typescript
    /**
     * COSMETIC-ONLY COMPONENT (Phase 1)
     * no backend intent-classification or routing logic exists yet; any LLM-driven
     * schema routing is a parked, unevaluated future direction; these values are
     * captured in local state only and will just be passed as plain fields alongside
     * the upload once Phase 2 exists. Do not wire them to any API call.
     */
    ```
  - `frontend/types/schema.ts` (lines 11–39): `resolveTabsForUpload(detectedKind)` is a static switch statement mapping `tabular` -> `[overview, forecast, stats, segmentation]`, `document` -> `[overview, summary]`, and `mixed` -> `[overview, summary, stats, segmentation]`. No dynamic routing is wired to backend logic.

### 1.4 Test Suite Status
- **Regression Test Suite**:
  - Command: `pytest backend/tests -k "not test_phase3a"`
  - Result: **180 passed, 0 failed, 18 deselected in 49.02s**. Complete zero regressions across existing Phase 2 security and ingestion tests.
- **Phase 3A Test Suite**:
  - Command: `pytest backend/tests/test_phase3a.py`
  - Result: **17 passed, 1 failed in 8.10s**.
  - Failing test verbatim error:
    ```text
    __________________ test_forecast_quality_and_latency_on_bike __________________
        def test_forecast_quality_and_latency_on_bike(bike_df):
            prep = fp.prepare_series(bike_df, target="cnt")
            run_forecast(prep)                                    # warm-up (xgboost import/JIT)
            res = run_forecast(prep, horizon=14)
            assert res["status"] == "ok" and len(res["forecast"]["dates"]) == 14
            assert res["metrics"]["ridge"]["r2"] > 0.5 or res["metrics"]["xgboost"]["r2"] > 0.5
    >       assert res["timing_ms"]["compute_total"] < 200, res["timing_ms"]
    E       AssertionError: {'features': 18.5, 'validation_fit': 148.0, 'refit_and_forecast': 115.0, 'compute_total': 281.5}
    E       assert 281.5 < 200
    backend\tests\test_phase3a.py:82: AssertionError
    ```

---

## 2. Logic Chain

1. **Synthetic Fixtures vs Physical Data**:
   - Observation 1.1 reveals that physical data on disk consists only of `benchmark_data.parquet` and `benchmark_data_ground_truth.parquet`.
   - In `backend/tests/conftest.py`, the 5 benchmark datasets are generated programmatically via numpy/pandas seeds (`bike_df`, `airline_df`, `retail_df`, `wholesale_df`, `promo_df`).
   - Therefore, no external large data files need to be committed to git or stored in `data/`, which satisfies the repository footprint constraints and enables reproducible testing.

2. **Ephemeral Memory Invariants**:
   - Spec §1 and §5.2 require that all transient session data be processed ephemerally with zero disk persistence.
   - Observation 1.2 demonstrates that `analytics_router.py` wraps both `/forecast` and `/hypotheses` endpoints in `with ephemeral_processing():`, processes bytes via `io.BytesIO`, deletes intermediate references explicitly (`del raw`, `del df`), and invokes `gc.collect()`.
   - Therefore, the data loading implementation strictly adheres to the ephemeral memory lifecycle invariant.

3. **Chart Orchestration and UI Dynamic Routing Boundary**:
   - User Rule §1 specifies: *"Dynamic UI schema and report chip routing is parked as a cosmetic placeholder and must NOT be wired to backend logic or routing."*
   - Observation 1.3 shows that backend `chart_picker.py` handles visualization recommendation purely by choosing from a fixed 4-element enum based on aggregated results, and frontend `ModeChips.tsx` is strictly client-side local state.
   - Therefore, existing code complies with the dynamic routing invariant.

4. **Latency Budget & Test Failure Analysis**:
   - `test_forecast_quality_and_latency_on_bike` fails because `compute_total` measures 281.5ms – 305.8ms against the 200ms assertion threshold.
   - Tracing `run_forecast()` in `backend/src/analytics/forecast_engine.py`:
     - Line 103 fits Ridge AND XGBoost on training rows (148ms).
     - Line 122 refits the winning model on all valid rows (115ms).
     - `XGB_PARAMS` configures `n_estimators=100`, `max_depth=4`, `n_jobs=1`.
     - Fitting 100 trees twice sequentially in single-threaded mode on Windows consumes ~263ms.
   - Downstream implementer can easily resolve this by either tuning `n_estimators` (e.g. 40–50), setting `n_jobs=-1`, or aligning the test latency threshold with the 200ms/300ms budget under Windows runner environments.

---

## 3. Caveats

- **No Caveats on Codebase Exploration**: All target areas (datasets, fixtures, ephemeral utilities, chart orchestrator, dynamic routing, and test suites) were directly read and verified with tool execution.
- **Hardware-Dependent Latency**: The exact millisecond breakdown of `run_forecast()` varies slightly between machine runs (281.5ms vs 305.8ms), but consistently exceeds 200ms due to sequential double fitting of 100 XGBoost estimators.

---

## 4. Conclusion

1. **Benchmark Datasets**: All 5 benchmark datasets needed for Phase 3A (`bike_df`, `airline_df`, `retail_df`, `wholesale_df`, `promo_df`) are already implemented as clean, self-contained fixtures in `backend/tests/conftest.py`. No physical data files need to be generated or stored in `data/`.
2. **Phase 2 Ingestion & Memory Architecture**: Fully in place and functional. `ephemeral_processing()` in `backend/src/memory/lifecycle.py`, in-memory stream loading in `backend/src/analytics/loader.py`, numeric downcasting in `tabular_parser.py`, and security sanitization (MIME/extension disagreement check, formula prefix neutralization) in `sanitization.py` meet all spec requirements.
3. **Chart Orchestrator & Dynamic Routing**: `backend/src/orchestrator/chart_picker.py` successfully encapsulates narrow LLM component recommendation with fallback to `heuristic_pick()`. The dynamic UI routing placeholder is strictly isolated in frontend components (`ModeChips.tsx`, `schema.ts`) and is not wired to backend endpoints.
4. **Readiness & Next Steps**:
   - All 180 existing Phase 2 tests pass (0 regressions).
   - 17 of 18 Phase 3A tests pass immediately.
   - To make `test_phase3a.py` 100% green, the implementer only needs to adjust XGBoost tree configuration or parallelization in `forecast_engine.py` (or adjust the latency assertion threshold) so `test_forecast_quality_and_latency_on_bike` completes within its target threshold.

---

## 5. Verification Method

To independently verify all observations and test results:

1. **Verify Artifact Footprint (< 50.0 MB)**:
   ```bash
   python backend/scripts/audit_artifact_size.py
   ```
   *Expected output*: 10 artifacts, 2.53 MB total size, `[PASSED]`.

2. **Verify Existing Phase 2 Test Suite (180 Tests Passing, 0 Regressions)**:
   ```bash
   pytest backend/tests -k "not test_phase3a"
   ```
   *Expected output*: `180 passed, 18 deselected`.

3. **Verify Phase 3A Test Suite Status**:
   ```bash
   pytest backend/tests/test_phase3a.py
   ```
   *Expected output*: `17 passed, 1 failed` (failure isolated to `test_forecast_quality_and_latency_on_bike` timing).

4. **Verify Ephemeral Processing Implementation**:
   Inspect `backend/src/memory/lifecycle.py` and `backend/src/api/analytics_router.py` lines 68 and 102.

5. **Verify Dynamic Routing Guardrail**:
   Inspect `frontend/components/query/ModeChips.tsx` lines 3–10 and `frontend/types/schema.ts`.
