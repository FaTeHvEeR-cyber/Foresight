"""Unit tests for backend/src/parsers/sanitization.py."""

import numpy as np
import pandas as pd
import pytest

from config.settings import settings
from src.parsers.sanitization import (
    FileSizeError,
    MimeTypeError,
    sanitize_tabular_cells,
    validate_file_size,
    validate_mime_and_extension,
)


# ============================================================================
# 1. MIME and Extension Validation Tests (including renamed file defenses)
# ============================================================================


@pytest.mark.parametrize(
    "filename,content_type",
    [
        ("dataset.csv", "text/csv"),
        ("dataset.csv", "text/plain"),
        ("dataset.csv", "application/vnd.ms-excel"),
        ("data.tsv", "text/tab-separated-values"),
        ("data.tsv", "text/plain"),
        ("data.tsv", "text/csv"),
        ("sheet.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("table.xls", "application/vnd.ms-excel"),
        ("records.parquet", "application/vnd.apache.parquet"),
        ("records.parquet", "application/x-parquet"),
        ("records.parquet", "application/octet-stream"),
        ("whitepaper.pdf", "application/pdf"),
        ("brief.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("notes.txt", "text/plain"),
        ("readme.md", "text/markdown"),
        ("readme.md", "text/plain"),
    ],
)
def test_validate_mime_and_extension_valid_pairs(filename, content_type):
    """Verify all valid pairings pass validation and return True."""
    assert validate_mime_and_extension(filename, content_type) is True


def test_validate_mime_and_extension_header_normalization():
    """Verify parameters like charset and uppercase headers are properly normalized."""
    assert validate_mime_and_extension("DATA.CSV", "TEXT/CSV; charset=utf-8") is True
    assert validate_mime_and_extension("notes.TXT", "text/plain; charset=ISO-8859-1") is True


@pytest.mark.parametrize(
    "filename,content_type",
    [
        ("data.csv", "application/pdf"),
        ("report.pdf", "text/csv"),
        ("malware.csv", "application/octet-stream"),
        ("notes.txt", "application/octet-stream"),
        ("summary.docx", "text/plain"),
        ("sheet.xlsx", "text/plain"),
        ("data.csv", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("dossier.pdf", "application/vnd.ms-excel"),
    ],
)
def test_validate_mime_and_extension_rejects_renamed_disagreement(filename, content_type):
    """Reject when declared MIME type and file extension disagree, even if both are individually allowed."""
    with pytest.raises(MimeTypeError) as exc_info:
        validate_mime_and_extension(filename, content_type)
    assert exc_info.value.status_code == 415
    assert "disagrees with file extension" in exc_info.value.detail


@pytest.mark.parametrize(
    "filename,content_type",
    [
        ("malware.exe", "application/octet-stream"),
        ("script.py", "text/plain"),
        ("index.html", "text/html"),
        ("archive.zip", "application/zip"),
        ("blob.bin", "application/octet-stream"),
    ],
)
def test_validate_mime_and_extension_disallowed_extension(filename, content_type):
    """Reject extensions not present in settings.ALLOWED_EXTENSIONS."""
    with pytest.raises(MimeTypeError) as exc_info:
        validate_mime_and_extension(filename, content_type)
    assert exc_info.value.status_code == 415
    assert "Unsupported file extension" in exc_info.value.detail


def test_validate_mime_and_extension_disallowed_mime():
    """Reject MIME types not in settings.ALLOWED_MIME_TYPES."""
    with pytest.raises(MimeTypeError) as exc_info:
        validate_mime_and_extension("data.csv", "application/json")
    assert exc_info.value.status_code == 415
    assert "Unsupported MIME type" in exc_info.value.detail


@pytest.mark.parametrize(
    "filename,content_type",
    [
        ("", "text/csv"),
        ("   ", "text/csv"),
        ("no_extension", "text/csv"),
        ("file.", "text/csv"),
        (".csv", "text/csv"),
        ("data.csv", ""),
        ("data.csv", "   "),
    ],
)
def test_validate_mime_and_extension_malformed_inputs(filename, content_type):
    """Reject empty, missing, or extension-less inputs."""
    with pytest.raises(MimeTypeError):
        validate_mime_and_extension(filename, content_type)


# ============================================================================
# 2. File Size Guardrail Validation Tests
# ============================================================================


def test_validate_file_size_valid():
    """Accept sizes strictly below and exactly at the 25MB boundary."""
    assert validate_file_size(b"sample data content") is True
    assert validate_file_size(1024) is True

    # Exactly at boundary
    exact_limit_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    assert validate_file_size(exact_limit_bytes) is True


def test_validate_file_size_oversized():
    """Reject file size strictly exceeding MAX_FILE_SIZE_MB with HTTP 413 FileSizeError."""
    limit_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    oversized = limit_bytes + 1

    with pytest.raises(FileSizeError) as exc_info:
        validate_file_size(oversized)
    assert exc_info.value.status_code == 413
    assert f"{settings.MAX_FILE_SIZE_MB}MB limit" in exc_info.value.detail


def test_validate_file_size_empty():
    """Reject 0-byte or empty payloads with HTTP 400 FileSizeError."""
    with pytest.raises(FileSizeError) as exc_bytes:
        validate_file_size(b"")
    assert exc_bytes.value.status_code == 400
    assert "Empty file" in exc_bytes.value.detail

    with pytest.raises(FileSizeError) as exc_int:
        validate_file_size(0)
    assert exc_int.value.status_code == 400


def test_validate_file_size_invalid_type():
    """Raise TypeError on unsupported types, including boolean and invalid containers."""
    with pytest.raises(TypeError):
        validate_file_size(["not", "bytes"])  # type: ignore

    with pytest.raises(TypeError):
        validate_file_size(True)  # type: ignore

    with pytest.raises(TypeError):
        validate_file_size(False)  # type: ignore


# ============================================================================
# 3. Tabular Formula-Injection Sanitization Tests
# ============================================================================


def test_sanitize_tabular_cells_prepends_quote_by_default():
    """Verify default mode neutralizes formula prefixes (=, @, +, -) by prepending a single quote."""
    df = pd.DataFrame({
        "id": [1, 2, 3, 4],
        "formula_col": ["=cmd|' /C calc'!A0", "@SUM(1+1)", "+100_percent", "-exploit_payload"],
        "safe_text": ["normal text", "hello world", "just a string", "safe"],
        "numeric_num": [10.5, -42.0, 0.0, 99.9],
        "bool_col": [True, False, True, False],
    })

    clean_df = sanitize_tabular_cells(df)

    # Formula injection strings neutralized
    assert clean_df["formula_col"].iloc[0] == "'=cmd|' /C calc'!A0"
    assert clean_df["formula_col"].iloc[1] == "'@SUM(1+1)"
    assert clean_df["formula_col"].iloc[2] == "'+100_percent"
    assert clean_df["formula_col"].iloc[3] == "'-exploit_payload"

    # None of the values should start with =, @, +, -
    for val in clean_df["formula_col"]:
        assert not val.startswith(("=", "@", "+", "-"))
        assert val.startswith("'")

    # Safe text left completely intact
    assert clean_df["safe_text"].tolist() == ["normal text", "hello world", "just a string", "safe"]

    # Numeric and boolean columns untouched
    assert clean_df["numeric_num"].tolist() == [10.5, -42.0, 0.0, 99.9]
    assert clean_df["bool_col"].tolist() == [True, False, True, False]


def test_sanitize_tabular_cells_strip_mode():
    """Verify strip mode strips the formula-injection prefix characters."""
    df = pd.DataFrame({
        "formula_col": ["=SUM(A1:B1)", "@ALERT", "+positive", "-negative"],
        "safe_col": ["clean", "data", "point", "text"],
    })

    clean_df = sanitize_tabular_cells(df, method="strip")

    assert clean_df["formula_col"].iloc[0] == "SUM(A1:B1)"
    assert clean_df["formula_col"].iloc[1] == "ALERT"
    assert clean_df["formula_col"].iloc[2] == "positive"
    assert clean_df["formula_col"].iloc[3] == "negative"

    # Also test convenience flag strip_prefix=True
    clean_df_flag = sanitize_tabular_cells(df, strip_prefix=True)
    assert clean_df_flag["formula_col"].iloc[0] == "SUM(A1:B1)"


def test_sanitize_tabular_cells_preserves_immutability():
    """Verify the original DataFrame is not modified in-place."""
    original_val = "=DANGEROUS_FORMULA"
    df = pd.DataFrame({"col": [original_val]})

    clean_df = sanitize_tabular_cells(df)

    assert df["col"].iloc[0] == original_val
    assert clean_df["col"].iloc[0] == f"'{original_val}"


def test_sanitize_tabular_cells_handles_nulls_and_empty():
    """Verify None, np.nan, and empty DataFrames are handled cleanly."""
    df = pd.DataFrame({
        "mixed": ["=attack", None, np.nan, "safe", ""],
    })

    clean_df = sanitize_tabular_cells(df)
    assert clean_df["mixed"].iloc[0] == "'=attack"
    assert pd.isna(clean_df["mixed"].iloc[1])
    assert pd.isna(clean_df["mixed"].iloc[2])
    assert clean_df["mixed"].iloc[3] == "safe"
    assert clean_df["mixed"].iloc[4] == ""

    # Empty df
    empty_df = pd.DataFrame()
    assert sanitize_tabular_cells(empty_df).empty


def test_sanitize_tabular_cells_categorical_series():
    """Verify Categorical columns are correctly sanitized."""
    df = pd.DataFrame({
        "cat": pd.Categorical(["=formula_cat", "normal_cat", "=formula_cat"]),
    })

    clean_df = sanitize_tabular_cells(df)
    assert clean_df["cat"].iloc[0] == "'=formula_cat"
    assert clean_df["cat"].iloc[1] == "normal_cat"
    assert clean_df["cat"].iloc[2] == "'=formula_cat"


def test_csv_quoted_commas_in_header_not_miscounted():
    """Verify CSV header pre-scan with quoted commas does not falsely exceed column limit."""
    # 6,000 columns with quoted commas (e.g. "col,1", "col,2", ...).
    # Actual column count is 6,000 (within 10,000 column limit).
    # But naive byte count of comma finds 11,999 commas, falsely triggering HTTP 422.
    headers = [f'"col,{i}"' for i in range(6000)]
    row = ["1"] * 6000
    csv_bytes = (",".join(headers) + "\n" + ",".join(row) + "\n").encode("utf-8")

    from src.parsers.sanitization import check_dangerous_and_magic_bytes
    # Should not raise HTTPException(422) now that quoted commas are respected
    check_dangerous_and_magic_bytes(csv_bytes, "csv")


def test_tsv_quoted_tabs_in_header_not_miscounted():
    """Verify TSV header pre-scan with quoted tabs does not falsely miscount columns."""
    from src.parsers.sanitization import check_dangerous_and_magic_bytes
    tsv_bytes = b'"col\t1"\t"col\t2"\tcol3\tcol4\tcol5\n1\t2\t3\t4\t5\n'
    # Should pass without error for 5 columns
    check_dangerous_and_magic_bytes(tsv_bytes, "tsv")


def test_csv_embedded_newline_in_quoted_header():
    """Verify CSV header pre-scan correctly parses header record with embedded newline in quotes."""
    from src.parsers.sanitization import check_dangerous_and_magic_bytes
    csv_bytes = b'"col1\nsubheading",col2,"col3\nversion"\n1,2,3\n'
    check_dangerous_and_magic_bytes(csv_bytes, "csv")


def test_csv_bom_prefixed_header_parsed():
    """Verify CSV header pre-scan correctly handles UTF-8 BOM prefix."""
    from src.parsers.sanitization import check_dangerous_and_magic_bytes
    bom_csv = b'\xef\xbb\xbf"col1","col2",col3\n1,2,3\n'
    check_dangerous_and_magic_bytes(bom_csv, "csv")


def test_csv_header_exactly_at_and_above_column_cap():
    """Verify CSV header exactly at the 10,000 column cap passes, and 10,001 columns raises HTTP 422."""
    from fastapi import HTTPException
    from src.parsers.sanitization import check_dangerous_and_magic_bytes

    # Exactly at cap (10,000 columns)
    at_cap_headers = [f"c{i}" for i in range(10_000)]
    at_cap_bytes = (",".join(at_cap_headers) + "\n1\n").encode("utf-8")
    check_dangerous_and_magic_bytes(at_cap_bytes, "csv")

    # One above cap (10,001 columns)
    above_cap_headers = [f"c{i}" for i in range(10_001)]
    above_cap_bytes = (",".join(above_cap_headers) + "\n1\n").encode("utf-8")
    with pytest.raises(HTTPException) as exc_info:
        check_dangerous_and_magic_bytes(above_cap_bytes, "csv")
    assert exc_info.value.status_code == 422
    assert "Table column count exceeds maximum limit" in exc_info.value.detail
    assert "10,001 columns found" in exc_info.value.detail


def test_csv_unterminated_quote_in_header():
    """Verify unterminated quote in CSV header returns controlled HTTP 422, never 5xx."""
    from fastapi import HTTPException
    from src.parsers.sanitization import check_dangerous_and_magic_bytes

    unterminated_csv = b'"col1,col2,col3\n1,2,3\n'
    with pytest.raises(HTTPException) as exc_info:
        check_dangerous_and_magic_bytes(unterminated_csv, "csv")
    assert exc_info.value.status_code == 422
    assert "Malformed CSV/TSV table header record" in exc_info.value.detail


def test_csv_10mb_header_only_hits_single_field_cap():
    """Verify a 10 MB header-only line hits the single-field cap (HTTP 413) quickly without hanging."""
    import time
    from fastapi import HTTPException
    from src.parsers.sanitization import check_dangerous_and_magic_bytes

    huge_header_line = b"col1," + (b"A" * (10 * 1024 * 1024 + 1024))
    t0 = time.perf_counter()
    with pytest.raises(HTTPException) as exc_info:
        check_dangerous_and_magic_bytes(huge_header_line, "csv")
    elapsed = time.perf_counter() - t0

    assert exc_info.value.status_code == 413
    assert "Single field or row length exceeds maximum limit" in exc_info.value.detail
    assert elapsed < 1.0, f"Single-field cap check took too long: {elapsed:.3f}s"


