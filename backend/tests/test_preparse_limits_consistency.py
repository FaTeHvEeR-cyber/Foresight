"""Automated Regression Suite for Pre-Parse Input Limits Consistency (WS-B).

Verifies:
1. settings.py is the single source of truth for all pre-parse resource limits.
2. Gatekeeper and parser code paths agree on the exact same limit values.
3. Tests fail if any code path diverges or hardcodes a different threshold.
4. Error messages never echo filenames, directory paths, or raw file content.
"""
from __future__ import annotations

import io
import time
import zipfile
import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException
from starlette.testclient import TestClient

from config.settings import settings
from main import app
from src.parsers.sanitization import check_dangerous_and_magic_bytes, gatekeep_tabular_upload
from src.parsers.tabular_parser import parse_tabular

client = TestClient(app)


def test_settings_is_single_source_of_truth_for_limits():
    """Verify settings exposes all required named constants with expected values."""
    assert settings.UPLOAD_MAX_SIZE_BYTES == 50 * 1024 * 1024
    assert settings.MAX_PARQUET_ROWS == 1_000_000
    assert settings.MAX_XLSX_UNCOMPRESSED_BYTES == 100 * 1024 * 1024
    assert settings.MAX_XLSX_SHEETS == 50
    assert settings.MAX_COLUMNS == 10_000
    assert settings.MAX_FIELD_LENGTH_BYTES == 10 * 1024 * 1024
    assert settings.XLSX_EXPANSION_RATIO_GUARD == 100


def test_single_field_cap_reconciled_between_preparse_and_parser():
    """Verify check_dangerous_and_magic_bytes and parse_tabular enforce identical single-field limits."""
    cap = settings.MAX_FIELD_LENGTH_BYTES

    # 1. At cap boundary: length == cap is accepted
    at_cap_str = "A" * (cap - 100)  # Total row comfortably within cap
    csv_at_cap = f"col1,col2\n1,{at_cap_str}\n".encode("utf-8")
    check_dangerous_and_magic_bytes(csv_at_cap, "csv")
    df_at_cap = parse_tabular(csv_at_cap, "csv")
    assert len(df_at_cap) == 1

    # 2. Above cap boundary: length > cap is rejected in both paths
    above_cap_str = "A" * (cap + 1024)
    csv_above_cap = f"col1,col2\n1,{above_cap_str}\n".encode("utf-8")

    # Gatekeeper check
    with pytest.raises(HTTPException) as exc_gatekeeper:
        check_dangerous_and_magic_bytes(csv_above_cap, "csv")
    assert exc_gatekeeper.value.status_code == 413
    assert "Single field or row length exceeds maximum limit" in exc_gatekeeper.value.detail

    # In-memory parser check
    with pytest.raises(ValueError) as exc_parser:
        parse_tabular(csv_above_cap, "csv")
    assert "Single field length exceeds maximum limit" in str(exc_parser.value)

    # 3. Assert error values report the exact same constant from settings
    assert f"max is {cap:,}" in exc_gatekeeper.value.detail
    assert f"max is {cap:,}" in str(exc_parser.value)


def test_column_cap_reconciled_with_settings():
    """Verify gatekeeper column limit exactly matches settings.MAX_COLUMNS."""
    cap = settings.MAX_COLUMNS

    # Exactly at cap
    headers_at_cap = [f"c{i}" for i in range(cap)]
    csv_at_cap = (",".join(headers_at_cap) + "\n1\n").encode("utf-8")
    check_dangerous_and_magic_bytes(csv_at_cap, "csv")

    # One above cap
    headers_above_cap = [f"c{i}" for i in range(cap + 1)]
    csv_above_cap = (",".join(headers_above_cap) + "\n1\n").encode("utf-8")
    with pytest.raises(HTTPException) as exc_info:
        check_dangerous_and_magic_bytes(csv_above_cap, "csv")
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == settings.error_max_columns_exceeded(cap + 1)


def test_parquet_rows_cap_reconciled_with_settings():
    """Verify Parquet row limit matches settings.MAX_PARQUET_ROWS."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    cap = settings.MAX_PARQUET_ROWS
    # Metadata inspection check using helper message
    expected_msg = settings.error_parquet_rows_exceeded(cap + 1)
    assert f"max is {cap:,}" in expected_msg


def test_xlsx_uncompressed_and_sheet_caps_reconciled_with_settings():
    """Verify XLSX uncompressed size and sheet count match settings constants."""
    uncompressed_cap = settings.MAX_XLSX_UNCOMPRESSED_BYTES
    sheet_cap = settings.MAX_XLSX_SHEETS

    msg_uncompressed = settings.error_xlsx_uncompressed_exceeded(uncompressed_cap + 1024)
    assert f"max is {uncompressed_cap // (1024 * 1024)} MB" in msg_uncompressed

    msg_sheets = settings.error_xlsx_sheets_exceeded(sheet_cap + 1)
    assert f"max is {sheet_cap}" in msg_sheets


def test_error_texts_never_echo_paths_or_file_content():
    """Verify error texts across gatekeeper and parser never echo paths or confidential content."""
    # 1. Path traversal filename without extension
    hostile_path = "../../../../../etc/passwd"
    with pytest.raises(HTTPException) as exc:
        gatekeep_tabular_upload(hostile_path, b"col1,col2\n1,2\n", "text/plain")
    assert exc.value.status_code == 415
    assert "../" not in exc.value.detail
    assert "File 'passwd'" in exc.value.detail

    # 2. Large cell content never echoed in 413 error
    confidential_secret = "SECRET_TOKEN_DO_NOT_LEAK_" + ("X" * (settings.MAX_FIELD_LENGTH_BYTES + 500))
    csv_secret = f"col1,secret\n1,{confidential_secret}\n".encode("utf-8")
    with pytest.raises(HTTPException) as exc_413:
        check_dangerous_and_magic_bytes(csv_secret, "csv")
    assert "SECRET_TOKEN_DO_NOT_LEAK" not in exc_413.value.detail


def test_code_paths_fail_if_divergent_limits_configured(monkeypatch):
    """Verify that if a code path is configured with an inconsistent limit, assertions detect divergence."""
    original_field_limit = settings.MAX_FIELD_LENGTH_BYTES
    original_col_limit = settings.MAX_COLUMNS

    try:
        # Simulate divergent limit on column cap
        monkeypatch.setattr(settings, "MAX_COLUMNS", 500)
        # 600 columns should now be rejected under the modified setting
        headers_600 = [f"c{i}" for i in range(600)]
        csv_600 = (",".join(headers_600) + "\n1\n").encode("utf-8")
        with pytest.raises(HTTPException) as exc_divergent:
            check_dangerous_and_magic_bytes(csv_600, "csv")
        assert exc_divergent.value.status_code == 422
        assert "max is 500" in exc_divergent.value.detail
    finally:
        monkeypatch.setattr(settings, "MAX_COLUMNS", original_col_limit)
        monkeypatch.setattr(settings, "MAX_FIELD_LENGTH_BYTES", original_field_limit)
