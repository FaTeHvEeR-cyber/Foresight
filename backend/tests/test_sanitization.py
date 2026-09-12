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
    """Raise TypeError on unsupported types."""
    with pytest.raises(TypeError):
        validate_file_size(["not", "bytes"])  # type: ignore


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
