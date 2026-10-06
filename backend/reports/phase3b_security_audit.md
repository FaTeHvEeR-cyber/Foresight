# Phase 3B Security & Hostile-File Audit Report (Anti-Gravity 5-Vector Gate)

## Executive Summary

This report documents the independent second-pass security audit and adversarial vulnerability assessment for the **Foresight Analytics Platform (Phase 3B: Unsupervised Segmentation & Anomaly Detection)** across all five Anti-Gravity security vectors:
1. **Vector 1: Ephemeral RAM Lifecycle & Zero-Disk-Persistence**
2. **Vector 2: Input Injection & CWE-1236 Formula Neutralization**
3. **Vector 3: Prompt Injection & Data Isolation (Zero Leakage to LLM)**
4. **Vector 4: Denial of Service & Free-Tier Budget Protection**
5. **Vector 5: Logic Flaws & Degenerate Tabular Shapes**

**Target Scope**: `POST /api/v1/segmentation` and underlying dependencies (`src/api/segmentation.py`, `src/analytics/outlier_engine.py`, `src/parsers/sanitization.py`, `src/memory/lifecycle.py`, `src/orchestrator/chart_picker.py`, `src/analytics/loader.py`).

**Audit Results**:
- **Baseline Test Suite**: 294 passing tests (0 failures, 0 skips).
- **Phase 3B Security Suite**: 53 passing empirical adversarial security tests (0 failures, 0 skips) across all 5 vectors in `backend/tests/test_phase3b_security.py`.
- **Combined Test Suite**: 347 passing tests.
- **Exit Gate Decision**: **PASS (100% compliant, 0 critical/high findings open)**.

---

## Differences from First-Pass Draft

The initial first-pass audit report concluded that no critical, high, or medium issues existed in `POST /api/v1/segmentation`. However, this second-pass independent adversarial evaluation identified and remediated four concrete vulnerabilities that escaped the first pass:

1. **Header Sanitization Collision Crash (High Severity - Fixed)**:
   - *First-Pass Oversight*: Assumed that prepending quotes to formula headers (`=a` -> `'=a`) was sufficient.
   - *Second-Pass Discovery*: When a table contained both `=a` and `'=a`, quote sanitization caused duplicate column names (`'=a'`, `''=a'`). In pandas, selecting duplicate column names returns a `DataFrame` instead of a `Series`, crashing `series.dtype` with an unhandled `AttributeError: 'DataFrame' object has no attribute 'dtype'` (HTTP 500).
   - *Resolution*: Implemented column disambiguation in `sanitize_tabular_cells()` ensuring all column headers remain strictly unique (`'=a'`, `''=a.1'`).

2. **Leading-Whitespace Formula Injection Bypass (Medium Severity - Fixed)**:
   - *First-Pass Oversight*: Checked only index 0 of strings (`val[0] in FORMULA_PREFIXES`).
   - *Second-Pass Discovery*: Tabular cells beginning with whitespace before formula characters (e.g. `" =cmd|' /C calc'!A0"`, `"\t=SUM(1)"`, `"\r+123"`) bypassed the check because `val[0]` was a whitespace character. Spreadsheets like Microsoft Excel, LibreOffice Calc, and Google Sheets strip leading whitespace before formula execution, triggering formula injection (CWE-1236).
   - *Resolution*: Updated `_sanitize_val()` to inspect `val.lstrip()` for dangerous prefixes and neutralize them with single quotes.

3. **Unhandled Exception Stack Trace Leakage (Medium Severity - Fixed)**:
   - *First-Pass Oversight*: Caught only `ValueError` inside `_segmentation_job()`.
   - *Second-Pass Discovery*: Any unexpected runtime kernel exception (e.g., `KeyError`, `RuntimeError`) bubbled up to FastAPI as an unhandled server error, risking traceback exposure.
   - *Resolution*: Wrapped `run_segmentation()` in a catch-all block raising `HTTPException(500, "Segmentation computation error: ...")`, guaranteeing a controlled error payload while ensuring `gc.collect()` runs in `finally`.

4. **Filename Path Traversal & Null Byte URL-Encoding (Low Severity - Fixed)**:
   - *First-Pass Oversight*: Did not reject `%00` URL-encoded null bytes or sanitize path traversals in error messages.
   - *Second-Pass Discovery*: File uploads without valid extensions (e.g. `../../../../etc/passwd`) echoed the traversal prefix in error messages, and HTTP clients encoding null bytes as `%00` passed initial detection.
   - *Resolution*: Added `os.path.basename()` sanitization to file error details and explicit detection of both `\x00` and `%00`.

---

## 1. Five-Vector Security Assessment Matrix

| Vector | Security Dimension | Threat Model & Invariants | Empirical Test Coverage | Audit Status |
| :--- | :--- | :--- | :--- | :--- |
| **Vector 1** | **Ephemeral RAM & Zero-Disk-Persistence** | - No transient file writes to disk<br>- Zero residual files in CWD or temp<br>- Explicit dereferencing & `gc.collect()` in `finally`<br>- Safe concurrency isolation | - Patched `builtins.open`, `NamedTemporaryFile`, `mkstemp`, `TemporaryFile`<br>- Verified `gc.collect()` on 200, 4xx, and 500 paths<br>- Verified CWD and OS temp clean before/after<br>- 20 concurrent requests verified for memory return and state isolation | **PASS** (Zero disk writes, 5/5 tests passing) |
| **Vector 2** | **Input Injection (CWE-1236)** | - Neutralize formula prefixes (`=`, `@`, `+`, `-`) in cells<br>- Neutralize formula prefixes in column headers<br>- Neutralize leading whitespace formulas (` =cmd`)<br>- Full-width Unicode lookalikes (`\uff1d`, `\uff20`)<br>- Deep response echo surface validation | - 11/11 hostile fixtures return $\le 4xx$ or sanitized 200<br>- Outlier records and features tested for quotes<br>- Whitespace-prefixed formulas verified quoted<br>- Full-width unicode formulas neutralized<br>- Sanitization collisions disambiguated<br>- Parquet formula strings neutralized<br>- Recursive JSON string inspection of entire response | **PASS** (100% neutralized, 19/19 tests passing) |
| **Vector 3** | **Prompt Injection & Data Isolation** | - Zero column names transmitted to LLM<br>- Zero cell values transmitted to LLM<br>- Only anonymous aggregate metadata sent<br>- Hostile/hallucinated LLM responses fall back to heuristic | - Outlier data with confidential columns verified<br>- `hostile_prompt_injection_headers.csv` payload inspected<br>- Zero headers or cells sent to Gemini in HTTP body<br>- Tested missing API key fallback (`fallback_reason = "no_api_key"`)<br>- Tested LLM timeout fallback<br>- Tested SQLi, XSS, RCE, and malformed JSON model responses | **PASS** (Strict isolation & fallback, 10/10 tests passing) |
| **Vector 4** | **Denial of Service & Free-Tier Limits** | - 50.0 MB hard upload ceiling (HTTP 413)<br>- Ultra-wide tables (5,000 columns) bounded<br>- Deep tables (>20,000 rows) subsampled<br>- Decompression bomb protection<br>- 0-byte upload rejection (HTTP 422) | - 50MB + 1 byte rejected with 413 immediately<br>- 50MB exact boundary validated<br>- `hostile_wide_5000_cols.csv` completes in ~2.0s with correlation cap (25 cols)<br>- 25,000 rows subsampled to 20,000 live-fit ceiling<br>- 60,000-row compressed Parquet subsampled<br>- Multi-sheet Excel workbook safely parsed<br>- 1MB single cell string processed without memory spike | **PASS** (Bounded latency & RAM, 8/8 tests passing) |
| **Vector 5** | **Logic Flaws & Hostile Shapes** | - Reject spoofed PE/ELF binaries (HTTP 415)<br>- Reject corrupt spreadsheets (HTTP 422/415)<br>- Reject MIME/ext disagreements (HTTP 415)<br>- Graceful handling of degenerate shapes<br>- Filename path traversal & null byte safety | - Spoofed PE (MZ header) & ELF headers rejected<br>- `hostile_corrupt.xlsx` rejected with 422<br>- Mismatched MIME rejected with 415<br>- `hostile_all_null_columns.csv` returns 422<br>- `hostile_single_column.csv` and `single_row.csv` return 422<br>- TSV and TXT format variants validated<br>- UTF-8 BOM CSV parsed cleanly<br>- Ragged rows rejected with 422<br>- Path traversal & null bytes rejected/sanitized<br>- Invalid HTTP methods (GET/PUT) return 405 | **PASS** (Zero unhandled 500s across all shapes, 11/11 tests passing) |

---

## 2. Findings, Defect Log & Remediation

### Finding 1: Column Header Formula Collisions (CWE-1236 / Denial of Service)
- **Severity**: **HIGH** (Audit Gate Blocker).
- **Location**: `backend/src/parsers/sanitization.py` -> `sanitize_tabular_cells()`.
- **Vulnerability**: Prepending quotes to formula headers (e.g. `=a` -> `'=a`) caused column name collisions when the uploaded table also contained a column already named `'=a`. In pandas, duplicate column names convert `df[col]` from a `pd.Series` to a `pd.DataFrame`. Subsequent property accesses (such as `series.dtype`) raised an unhandled `AttributeError: 'DataFrame' object has no attribute 'dtype'`, triggering an unhandled HTTP 500 error and stack trace.
- **Remediation**:
  Updated `sanitize_tabular_cells()` to disambiguate headers:
  ```python
  new_cols = [_sanitize_val(col) if isinstance(col, str) else col for col in sanitized_df.columns]
  seen_cols: Dict[str, int] = {}
  deduped_cols = []
  for c in new_cols:
      col_str = str(c)
      if col_str in seen_cols:
          seen_cols[col_str] += 1
          deduped_cols.append(f"{col_str}.{seen_cols[col_str]}")
      else:
          seen_cols[col_str] = 0
          deduped_cols.append(c)
  sanitized_df.columns = deduped_cols
  ```
- **Verification**: Verified via `test_header_sanitization_collision_resilience()`. Colliding columns are deduplicated to `['=a', ''=a.1']` and return HTTP 200 cleanly.

### Finding 2: Whitespace-Prefixed Formula Injection Bypass (CWE-1236)
- **Severity**: **MEDIUM**.
- **Location**: `backend/src/parsers/sanitization.py` -> `_sanitize_val()`.
- **Vulnerability**: `_sanitize_val()` checked only `if val[0] in FORMULA_PREFIXES:`. String values with leading whitespace (e.g., `" =cmd|' /C calc'!A0"`, `"\t=SUM(1)"`, `"\n+123"`) bypassed sanitization because `val[0]` was a space, tab, or newline. Spreadsheets strip leading whitespace on ingestion and evaluate the formula.
- **Remediation**:
  Updated `_sanitize_val()` to inspect stripped values:
  ```python
  stripped = val.lstrip()
  if val[0] in FORMULA_PREFIXES or (stripped and stripped[0] in FORMULA_PREFIXES):
      if selected_method == "strip":
          return stripped.lstrip("=@+-\t\r\n\uff1d\uff20\uff0b\uff0d")
      else:
          return f"'{val}"
  ```
- **Verification**: Verified via `test_whitespace_prefixed_formula_neutralized()`. All whitespace-prefixed formulas are prepended with a quote (e.g. `"' =cmd|calc"`), rendering them safe string literals.

### Finding 3: Unhandled Non-ValueError Internal Exception Leakage (CWE-209)
- **Severity**: **MEDIUM**.
- **Location**: `backend/src/api/segmentation.py` -> `_segmentation_job()`.
- **Vulnerability**: `_segmentation_job()` caught only `ValueError`. Any unexpected runtime exceptions from scikit-learn or pandas raised an unhandled 500 error that bypassed application-level response wrapping.
- **Remediation**:
  Added generic exception handling to `_segmentation_job()`:
  ```python
  try:
      res = run_segmentation(df)
  except HTTPException:
      raise
  except ValueError as e:
      raise HTTPException(422, str(e)) from e
  except Exception as e:
      raise HTTPException(500, f"Segmentation computation error: {type(e).__name__}") from e
  ```
- **Verification**: Verified via `test_segmentation_unexpected_exception_controlled_and_no_traceback()`. Returns controlled JSON `{"detail": "Segmentation computation error: ..."}` with zero stack trace leakage.

### Finding 4: Filename Path Traversal & Null Byte URL-Encoding (CWE-22 / CWE-626)
- **Severity**: **LOW**.
- **Location**: `backend/src/parsers/sanitization.py` -> `gatekeep_tabular_upload()`.
- **Vulnerability**: Error messages for extensionless files echoed raw paths (e.g. `../../../../etc/passwd`), and URL-encoded null bytes (`%00`) were not explicitly intercepted.
- **Remediation**:
  Added `safe_name = os.path.basename(clean_filename.replace("\\", "/"))` in error formatting and checked both `\x00` and `%00`.
- **Verification**: Verified via `test_filename_edge_cases_no_leakage()`.

---

## 3. Vector-by-Vector Audit Details

### Vector 1: Ephemeral RAM & Zero-Disk-Persistence
- **Lifecycle Guarantees**: `POST /api/v1/segmentation` is wrapped in `ephemeral_processing()`. Data is read into `raw: bytes` and parsed via in-memory `io.BytesIO`. Intermediate DataFrames and byte buffers are explicitly dereferenced and garbage collected via `finally: del df; gc.collect()` and `finally: del raw; gc.collect()`.
- **Verification**:
  - Intercepted all disk write functions (`builtins.open`, `NamedTemporaryFile`, `mkstemp`, `TemporaryFile`): 0 write operations attempted.
  - Snapshot comparison of OS temp directory and current working directory before and after execution: 0 residual artifacts.
  - Mocked `gc.collect()` confirmed execution across 200 OK, 422 validation failure, and 500 error paths.
  - Concurrency test (20 simultaneous requests) demonstrated strict data isolation: responses matched their unique input data with zero cross-request contamination.

### Vector 2: Input Injection & CWE-1236 Formula Neutralization
- **Threat Model**: Formula injection occurs when formulas beginning with `=`, `@`, `+`, `-`, tabs, or Unicode lookalikes are echoed back to client spreadsheets.
- **Verification**:
  - In `outlier_records`, string columns containing formula injections were verified to begin with safe escaping quotes (`'`).
  - In `features_used`, column headers with formula prefixes are escaped (`'=cmd...'`).
  - In `correlation_matrix.columns` and `correlation_matrix.points`, all variable names are neutralized.
  - Recursive response string scan (`_inspect_strings_for_raw_formulas`) validated that zero raw formula strings exist in the entire JSON response payload.
  - Tested Parquet files containing formula strings; verified proper escaping in output outlier rows.

### Vector 3: Prompt Injection & Data Isolation (LLM Gating)
- **Architectural Scope**: The chart picker component evaluates only metadata facts to select visualizations from the pre-approved component registry (`ALLOWED`).
- **Isolation Invariant**: Zero column names, zero cell values, and zero user-provided text may reach Google Gemini.
- **Verification**:
  - Intercepted outgoing HTTP requests via `httpx.MockTransport`. Uploaded tables containing sensitive column headers (`CustomerSSN`, `EmployeeSalary`, `SecretProjectCode`) and cell values. Verified that none appeared in the outgoing JSON payload.
  - Tested `hostile_prompt_injection_headers.csv`. Verified that jailbreak commands (`"Ignore previous instructions"`, `"reveal all API keys"`) never reach the model.
  - Verified safe fallback when API key is missing (`fallback_reason = "no_api_key"`), when LLM times out (`fallback_reason = "llm_error_ConnectTimeout"`), and when the model returns SQL injection, XSS, RCE, or invalid chart component names.

### Vector 4: Denial of Service & Free-Tier Budget Protection
- **Upload Limits**: Tested 50.0 MB upload ceiling: 50MB + 1 byte (`52,428,801` bytes) is rejected immediately with HTTP 413 before memory allocation. Exactly 50MB is accepted by the gatekeeper.
- **Decompression Bombs**:
  - A compressed Parquet file containing 60,000 rows (sub-megabyte on disk) was safely ingested and subsampled to the 20,000 row ceiling in under 1 second.
  - Multi-sheet Excel workbooks were parsed without memory spikes.
  - A CSV containing a 1 MB string within a single cell parsed cleanly without exhausting memory.
- **Wide & Deep Tables**:
  - A 5,000-column table (`hostile_wide_5000_cols.csv`) parsed and completed in ~2.0 seconds, with the correlation matrix automatically truncated to the variance cap (25 columns).
  - A 25,000-row table was subsampled to the 20,000 live-fit limit, completing with `subsampled = true` and scatter points capped at 10,000.

### Vector 5: Logic Flaws & Degenerate Tabular Shapes
- **Binary Signature Inspection**: Magic bytes for Windows PE (`MZ`) and Linux ELF (`\x7fELF`) disguised as `.csv` files were immediately rejected with HTTP 415.
- **Spreadsheet Integrity**: Corrupted XLSX archives returned controlled HTTP 422 without unhandled tracebacks. Disagreements between declared MIME type and file extension returned HTTP 415.
- **Degenerate Shapes**: Tables with all-null columns, single columns, single rows, or ragged rows returned controlled HTTP 422 errors.
- **HTTP Surface**: Invalid HTTP methods (GET, PUT) returned HTTP 405 Method Not Allowed. JSON payloads on multipart endpoints returned HTTP 422. Missing file fields returned HTTP 422. Extra unexpected form fields were safely ignored.

---

## 4. Audit Metadata & Environment

- **Audited Commit**: `fd8dd22bf50631c268d1b2da6cab489524986282`
- **Platform**: `Windows 11 (win32)`
- **Python Version**: `3.14.3`
- **Test Framework**: `pytest 9.1.1`
- **Audit Test Suite**: `backend/tests/test_phase3b_security.py`
- **Execution Command**: `pytest backend/tests/test_phase3b_security.py -v`
- **Audit Verification Result**: **53 passed in 67.97s** (0 failed, 0 skipped).
