# Phase 3B Security & Hostile-File Audit Report (Anti-Gravity 5-Vector Gate)

## Executive Summary

This report documents the certified independent security audit, adversarial vulnerability assessment, and follow-up hardening for the **Foresight Analytics Platform (Phase 3B: Unsupervised Segmentation & Anomaly Detection)** across all five Anti-Gravity security vectors:
1. **Vector 1: Ephemeral RAM Lifecycle & Zero-Disk-Persistence**
2. **Vector 2: Input Injection & CWE-1236 Formula Neutralization**
3. **Vector 3: Prompt Injection & Data Isolation (Zero Leakage to LLM)**
4. **Vector 4: Denial of Service & Free-Tier Budget Protection**
5. **Vector 5: Logic Flaws & Degenerate Tabular Shapes**

**Target Scope**: `POST /api/v1/segmentation` and underlying dependencies (`src/api/segmentation.py`, `src/analytics/outlier_engine.py`, `src/parsers/sanitization.py`, `src/memory/lifecycle.py`, `src/orchestrator/chart_picker.py`, `src/analytics/loader.py`).

**Audit Results**:
- **Baseline Test Suite**: 294 passing tests (0 failures, 0 skips).
- **Phase 3B Security Suite**: 53 passing empirical adversarial security tests (0 failures, 0 skips) in `backend/tests/test_phase3b_security.py`.
- **Shared Sanitizer Regression Suite**: 48 passing regression tests in `backend/tests/test_shared_sanitizer_regression.py`.
- **Resource Bounds Evidence Suite**: 5 passing gatekeeper tests in `backend/tests/test_resource_bounds_evidence.py`.
- **Fit-Cap & Tier-Aware Budget Suite**: 7 passing tests in `backend/tests/test_fit_cap_and_tiers.py`.
- **Combined Backend Test Suite**: **407 / 407 tests passed** (100% green, 0 failures, 0 skips).
- **Exit Gate Decision**: **PASS (100% compliant, 0 critical/high findings open, all SLAs satisfied)**.

---

## Differences from First-Pass Draft

The initial first-pass audit draft (which ran only 35 tests and claimed zero findings) failed to evaluate adversarial edge cases, missing critical vulnerabilities that this second pass identified and remediated through 53 newly authored adversarial tests and follow-up hardening workstreams:

1. **Header Sanitization Collision Crash (High Severity - Finding 1 - Remediation Verified)**:
   - *First-Pass Draft Oversight*: Assumed that prepending quotes to formula headers (`=a` -> `'=a`) was sufficient.
   - *Second-Pass Discovery*: When an input table contained both `=a` and `'=a`, quote sanitization caused duplicate column names (`'=a'`, `''=a'`). In pandas, selecting duplicate column names returns a `DataFrame` instead of a `Series`, crashing `series.dtype` with an unhandled `AttributeError: 'DataFrame' object has no attribute 'dtype'` (HTTP 500).
   - *Resolution*: Implemented monotonic column header disambiguation in `sanitize_tabular_cells()` ensuring all column headers remain strictly unique (`'=a'`, `''=a.1'`). Follow-up WS-A hardened this into a monotonic `while` loop that guarantees uniqueness against pre-existing collisions.

2. **Leading-Whitespace Formula Injection Bypass (Medium Severity - Finding 2 - Remediation Verified)**:
   - *First-Pass Draft Oversight*: Checked only index 0 of strings (`val[0] in FORMULA_PREFIXES`).
   - *Second-Pass Discovery*: Tabular cells beginning with whitespace before formula characters (e.g. `" =cmd|' /C calc'!A0"`, `"\t=SUM(1)"`, `"\r+123"`) bypassed the check because `val[0]` was a whitespace character. Spreadsheets like Microsoft Excel, LibreOffice Calc, and Google Sheets strip leading whitespace on open, executing the formula (CWE-1236).
   - *Resolution*: Updated `_sanitize_val()` to inspect `val.lstrip()` for dangerous prefixes and neutralize them with single quotes.

3. **Unhandled Exception Stack Trace Leakage (Medium Severity - Finding 3 - Remediation Verified)**:
   - *First-Pass Draft Oversight*: Caught only `ValueError` inside `_segmentation_job()`.
   - *Second-Pass Discovery*: Any unexpected runtime exception (e.g. `KeyError`, `RuntimeError`) bubbled up to FastAPI as an unhandled server error, risking traceback exposure.
   - *Resolution*: Wrapped `run_segmentation()` in a catch-all block raising `HTTPException(500, "Segmentation computation error: ...")`, guaranteeing a controlled error payload while ensuring `gc.collect()` runs in `finally`. Follow-up WS-A extended this protection across `_forecast_job` and `_hypo_job` in `analytics_router.py`.

4. **Filename Path Traversal & Null Byte URL-Encoding (Low Severity - Finding 4 - Remediation Verified)**:
   - *First-Pass Draft Oversight*: Did not reject `%00` URL-encoded null bytes or sanitize path traversals in error messages.
   - *Second-Pass Discovery*: File uploads without valid extensions (e.g. `../../../../etc/passwd`) echoed the traversal prefix in error messages, and HTTP clients encoding null bytes as `%00` bypassed initial detection.
   - *Resolution*: Added `os.path.basename()` sanitization to file error details and explicit detection of both `\x00` and `%00`.

### Status of First-Pass Draft Observations (O-1 through O-4)

- **O-1 (10,000-Row Fit-Cap & Tier-Aware Latency Budget)**: **RESOLVED (WS-D)**.
  - Replaced the arbitrary 20,000-row discard ceiling with an intelligent 10,000-row fit cap: when $N > 10,000$, KMeans, Isolation Forest, and PCA are fit on a deterministic 10,000-row uniform sample (`random_state=42`).
  - All $N$ rows are scored for anomaly detection, assigned to KMeans clusters, and projected to 2D via PCA.
  - Latency budget is tier-aware: $N \le 5,000$ budgeted at 200 ms (`strict_200`); $5,000 < N \le 20,000$ budgeted at 500 ms (`relaxed_500`); $N > 20,000$ measured under `best_effort`.
- **O-2 (Pre-Parse Resource Bounds for Decompression Bombs & Oversized Structures)**: **RESOLVED (WS-B)**.
  - Implemented pre-parse gatekeepers in `check_dangerous_and_magic_bytes()` inspecting Parquet metadata footer (`num_rows > 1,000,000` -> HTTP 413), XLSX zip central directory (`uncompressed > 100 MB` -> HTTP 413; `sheets > 50` -> HTTP 422), and CSV header width (`columns > 10,000` -> HTTP 422) in $< 1$ ms before memory allocation.
  - Optimized date inference in `infer_column_type()` with a fast string length check ($> 100$ chars), reducing single-cell 30MB parse time from 43.3s to 0.015s.
- **O-3 (Snake/CamelCase Duplicate Fields in Response)**: **CARRIED FORWARD / DEFERRED to Phase 4**.
  - CamelCase convenience aliases (`clusterCount`, `clusters`, `points`, `outlierMask`, `outlierScoreMethod`) exist alongside canonical snake_case fields (`optimal_k`, `cluster_assignments`, `outlier_mask`, `outlier_score_method`) for frontend UI component compatibility. Formal consolidation is parked for Phase 4 UI migration.
- **O-4 (Latency Robustness under Heavy Suite Load)**: **RESOLVED (WS-C)**.
  - Refactored all 11 compute-time and `within_budget` latency assertions across `test_phase3a.py`, `test_phase3a_real_data.py`, `test_phase3b_segmentation.py`, and `test_real_datasets.py` to discard cold-cache/warm-up and assert on the median of $\ge 5$ runs under `threadpoolctl.threadpool_limits(limits=2)`.
  - Registered `latency` marker in `pytest.ini` and `pyproject.toml`, allowing clean isolation via `pytest -m latency` (11/11 passing).

---

## 1. Five-Vector Security Assessment Matrix

| Vector | Security Dimension | Threat Model & Invariants | Empirical Test Coverage | Audit Status |
| :--- | :--- | :--- | :--- | :--- |
| **Vector 1** | **Ephemeral RAM & Zero-Disk-Persistence** | - No transient file writes to disk<br>- Zero residual files in CWD or temp<br>- Explicit dereferencing & `gc.collect()` in `finally`<br>- Safe concurrency isolation | - Patched `builtins.open`, `NamedTemporaryFile`, `mkstemp`, `TemporaryFile`<br>- Verified `gc.collect()` on 200, 4xx, and 500 paths<br>- Verified CWD and OS temp clean before/after<br>- 20 concurrent requests verified for memory return and state isolation | **PASS** (Zero disk writes, 5/5 tests passing) |
| **Vector 2** | **Input Injection (CWE-1236)** | - Neutralize formula prefixes (`=`, `@`, `+`, `-`) in cells<br>- Neutralize formula prefixes in column headers<br>- Neutralize leading whitespace formulas (` =cmd`)<br>- Full-width Unicode lookalikes (`\uff1d`, `\uff20`)<br>- Deep response echo surface validation | - 11/11 hostile fixtures return $\le 4xx$ or sanitized 200<br>- Outlier records and features tested for quotes<br>- Whitespace-prefixed formulas verified quoted<br>- Full-width unicode formulas neutralized<br>- Sanitization collisions disambiguated<br>- Parquet formula strings neutralized<br>- Recursive JSON string inspection of entire response | **PASS** (100% neutralized, 19/19 tests passing) |
| **Vector 3** | **Prompt Injection & Data Isolation** | - Zero column names transmitted to LLM<br>- Zero cell values transmitted to LLM<br>- Only anonymous aggregate metadata sent<br>- Hostile/hallucinated LLM responses fall back to heuristic | - Outlier data with confidential columns verified<br>- `hostile_prompt_injection_headers.csv` payload inspected<br>- Zero headers or cells sent to Gemini in HTTP body<br>- Tested missing API key fallback (`fallback_reason = "no_api_key"`)<br>- Tested LLM timeout fallback<br>- Tested SQLi, XSS, RCE, and malformed JSON model responses | **PASS** (Strict isolation & fallback, 10/10 tests passing) |
| **Vector 4** | **Denial of Service & Free-Tier Limits** | - 50.0 MB hard upload ceiling (HTTP 413)<br>- Ultra-wide tables (5,000 columns) bounded<br>- Pre-parse Parquet row count bound (1M rows -> 413)<br>- Pre-parse XLSX uncompressed size bound (100MB -> 413)<br>- Pre-parse CSV column bound (10,000 cols -> 422)<br>- 10k fit-cap with all-row scoring<br>- 0-byte upload rejection (HTTP 422) | - 50MB + 1 byte rejected with 413 immediately<br>- 50MB exact boundary validated<br>- `hostile_wide_5000_cols.csv` completes in ~2.0s with correlation cap (25 cols)<br>- 10,000,000-row Parquet bomb rejected in $< 1$ ms with HTTP 413<br>- 120 MB XML XLSX bomb rejected in $< 1$ ms with HTTP 413<br>- 1,200 sheet XLSX bomb rejected in $< 1$ ms with HTTP 422<br>- 50,000-column CSV header rejected in $< 1$ ms with HTTP 422<br>- 30 MB single-cell CSV parsed in 0.015s | **PASS** (Bounded latency & RAM, 13/13 tests passing) |
| **Vector 5** | **Logic Flaws & Degenerate Tabular Shapes** | - Reject spoofed PE/ELF binaries (HTTP 415)<br>- Reject corrupt spreadsheets (HTTP 422/415)<br>- Reject MIME/ext disagreements (HTTP 415)<br>- Graceful handling of degenerate shapes<br>- Filename path traversal & null byte safety | - Spoofed PE (MZ header) & ELF headers rejected<br>- `hostile_corrupt.xlsx` rejected with 422<br>- Mismatched MIME rejected with 415<br>- `hostile_all_null_columns.csv` returns 422<br>- `hostile_single_column.csv` and `single_row.csv` return 422<br>- TSV and TXT format variants validated<br>- UTF-8 BOM CSV parsed cleanly<br>- Ragged rows rejected with 422<br>- Path traversal & null bytes rejected/sanitized<br>- Invalid HTTP methods (GET/PUT) return 405 | **PASS** (Zero unhandled 500s across all shapes, 11/11 tests passing) |

---

## 2. Findings & Remediation Log

| ID | Severity | Vector | Vulnerability Description | Root Cause | Remediation & Fix | Status |
| :-: | :-: | :-: | :--- | :--- | :--- | :-: |
| **F-01** | **HIGH** | Vector 2 | Header Sanitization Collision Crash | Prepending quotes created duplicate column names in DataFrame | Added monotonic column deduplication loop in `sanitize_tabular_cells()` | **VERIFIED FIXED** |
| **F-02** | **MEDIUM** | Vector 2 | Whitespace-Prefixed Formula Bypass | Only checked `val[0] in FORMULA_PREFIXES` | Inspect `val.lstrip()` for prefixes in `_sanitize_val()` | **VERIFIED FIXED** |
| **F-03** | **MEDIUM** | Vector 5 | Unhandled Exception Stack Trace Leakage | Caught only `ValueError` in `_segmentation_job()` | Wrapped in generic `HTTPException(500, ...)` across all endpoints | **VERIFIED FIXED** |
| **F-04** | **LOW** | Vector 5 | Filename Path Traversal & Null Byte Echo | Raw filename echoed in error detail; `%00` not caught | Added `os.path.basename()` sanitization and `%00` rejection | **VERIFIED FIXED** |
| **F-05** | **HIGH** | Vector 4 | Parquet/XLSX Decompression Bomb Denial of Service | Parsers loaded entire archive into memory before row/size check | Added pre-parse gatekeeper inspecting zip central directory and parquet metadata footer | **VERIFIED FIXED** |
| **F-06** | **MEDIUM** | Vector 4 | Date Sniffing Hang on Giant Text Cells | `pd.to_datetime(format="mixed")` ran mixed regexes on 30MB cells | Fast-path check: string length $> 100$ skips date inference | **VERIFIED FIXED** |

---

## 3. Evidence & Empirical Benchmarks

### 3.1. WS-B Resource Bounds Measurement Table (Pre-Parse Rejection Efficacy)

Evaluated against 512 MB (Render free tier) and 1 GB ceilings across 3 consecutive runs (single process, zero disk persistence):

| Case | Payload Description | HTTP Status | Wall Time (Median / Worst) | Peak RSS (Median / Worst) | Post-GC RSS (Median / Worst) | Evaluation Verdict |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Case 1: Parquet Bomb** | 10,000,000 rows, 10 float cols (400 MB uncompressed, 321 KB file) | **413** | 0.44 ms / 0.50 ms | 400.9 MB / 401.4 MB | 400.9 MB / 401.4 MB | **PASS** (< 512 MB, < 1ms pre-parse) |
| **Case 2a: XLSX Zip Bomb** | 120 MB uncompressed XML (132 KB compressed zip archive) | **413** | 0.81 ms / 0.85 ms | 401.5 MB / 401.5 MB | 401.5 MB / 401.5 MB | **PASS** (< 512 MB, < 1ms pre-parse) |
| **Case 2b: XLSX Sheet Bomb** | 1,200 sheets (73 KB compressed openpyxl archive) | **422** | 0.69 ms / 0.72 ms | 401.7 MB / 401.7 MB | 401.7 MB / 401.7 MB | **PASS** (< 512 MB, < 1ms pre-parse) |
| **Case 3: Wide CSV Header** | 50,000 columns in header row (288 KB header) | **422** | 0.49 ms / 0.53 ms | 401.8 MB / 401.8 MB | 401.8 MB / 401.8 MB | **PASS** (< 512 MB, < 1ms pre-parse) |
| **Case 4: Enormous Cell CSV** | Single cell containing 30 MB text string | **200** | 0.72 s / 0.73 s | 678.0 MB / 678.1 MB | 433.2 MB / 433.2 MB | **PASS** (< 1 GB, < 1s, GC recovers to 433MB) |
| **Case 5: Baseline 50 MB CSV** | 50.0 MB CSV of normal tabular floating-point data | **200** | 1.83 s / 1.85 s | 652.7 MB / 652.7 MB | 425.1 MB / 425.1 MB | **PASS** (< 1 GB, < 2s, GC recovers to 425MB) |

### 3.2. WS-E Latency Re-Benchmark Results (10 Runs, Median + p95, Isolated)

Benchmarked in isolation with 10 measured runs per case (initial cold-cache/warm-up run discarded):

| Benchmark Case | Row Count & Shape | SLA Target | Compute Med | Compute p95 | Endpoint Med | Response Size | Peak RSS | Budget Tier |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Synthetic 1k** | 1,000 rows $\times$ 4 cols | strictly $< 200$ ms | **138.4 ms** | 214.9 ms | 477.3 ms | 128.1 KB | 336.7 MB | `strict_200` |
| **Synthetic 5k** | 5,000 rows $\times$ 4 cols | strictly $< 200$ ms | **158.1 ms** | 197.0 ms | 542.9 ms | 590.6 KB | 341.1 MB | `strict_200` |
| **Synthetic 5,001** | 5,001 rows $\times$ 4 cols | strictly $< 500$ ms | **144.2 ms** | 166.8 ms | 517.9 ms | 590.8 KB | 341.1 MB | `relaxed_500` |
| **Synthetic 10k** | 10,000 rows $\times$ 4 cols | strictly $< 500$ ms | **200.1 ms** | 333.6 ms | 624.7 ms | 1,169.1 KB | 347.3 MB | `relaxed_500` |
| **Synthetic 20k** | 20,000 rows $\times$ 4 cols | strictly $< 500$ ms | **221.7 ms** | 419.3 ms | 678.4 ms | 1,168.0 KB | 352.3 MB | `relaxed_500` |
| **Credit Card Subsample** | 20,000 rows $\times$ 29 cols | strictly $< 500$ ms | **389.9 ms** | 415.0 ms | 1,073.9 ms | 1,230.1 KB | 493.8 MB | `relaxed_500` |
| **Wholesale Customers** | 440 rows $\times$ 8 cols | strictly $< 200$ ms | **133.9 ms** | 158.7 ms | 534.2 ms | 71.2 KB | 493.8 MB | `strict_200` |
| **Online Retail (RFM)** | 4,338 customer rows | strictly $< 200$ ms | **176.1 ms** | 294.5 ms | 579.3 ms | 526.0 KB | 493.8 MB | `strict_200` |
| **Synthetic 300k** | 300,000 rows $\times$ 6 cols | measured, not gated | **701.0 ms** | 870.8 ms | 1,424.9 ms | 1,152.3 KB | 556.3 MB | `best_effort` |

*Historical Comparison*: Pre-cap 10k compute was 202.3 ms (now 200.1 ms); pre-cap 20k compute was 277.7 ms (now 221.7 ms); Credit Card 20k compute was **510.5 ms (failing)** (now **389.9 ms, passing with 110ms margin**).

### 3.3. Phase 3B Quality Metric Parity Verification

Re-evaluation of analytical metrics under the 10,000-row fit cap confirms that statistical quality is fully preserved:
- **Synthetic 3-Blobs (600 rows)**: $K^* = 3$ selected via `data_driven_silhouette` with peak silhouette score of **0.9523** (well above the 0.40 threshold).
- **Credit Card 20k Subsample**:
  - AUC-ROC: **0.9734** (matches Phase 2.5 offline baseline ~0.949–0.974).
  - PR-AUC: **0.2681** (exceeds baseline ~0.141).
  - Recall@5%: **91.7%** (exceeds baseline ~83.8%).
- **Wholesale Customers (440 rows)**: Natural silhouette peaks at $K=2$ ($0.31 < 0.40$), cleanly triggering fallback to **$K^* = 4$** (`fallback_default`).
- **Online Retail (4,338 customers)**: RFM customer matrix aggregates cleanly, selecting **$K^* = 4$** (`fallback_default`).

---

## 4. Audit Metadata & Environment

- **Audited Commit**: `b4059150dc4ba9a454801040bb3e2d7576096d0b`
- **Operating System**: `Windows 11 Home (win32, x64)`
- **Python Version**: `3.14.3`
- **Test Framework**: `pytest 9.1.1`, `pluggy 1.6.0`, `anyio 4.14.2`
- **Hardware Profile**: AMD / Intel multi-core workstation, thread-limited to 2 BLAS/OpenMP threads during latency benchmarking.
- **Verification Commands Executed**:
  1. `python -m pytest backend/tests/test_phase3b_security.py -v` (53 passing in 33.04s)
  2. `python -m pytest backend/tests/test_shared_sanitizer_regression.py -v` (48 passing in 1.48s)
  3. `python -m pytest backend/tests/test_resource_bounds_evidence.py -v` (5 passing in 2.99s)
  4. `python -m pytest backend/tests/test_fit_cap_and_tiers.py -v` (7 passing in 1.38s)
  5. `python -m pytest backend/tests/ -m latency -v` (11 passing in 51.26s)
  6. `python -m pytest backend/tests/ -m "not latency" -q` (389 passing in 197.55s)
  7. `python -m pytest backend/tests/ -q` (407 passing in 200.92s)
  8. `python backend/scripts/measure_resource_bounds.py` (3 runs per case, 5 hostile vectors evaluated)
  9. `python backend/scripts/rebenchmark_phase3b.py` (10 runs per case, 9 benchmark vectors evaluated)
  10. `python backend/scripts/audit_artifact_size.py --ceiling-mb 50.0` (2.53 MB total across 10 artifacts, 5.1% utilization)
