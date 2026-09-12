"""Comprehensive unit & integration tests for POST /upload in main.py."""

import io
import pytest
from starlette.testclient import TestClient
import pandas as pd
import numpy as np

from main import app, DATA_STORE


@pytest.fixture
def client():
    return TestClient(app)


def test_upload_tabular_csv_success(client):
    """Test successful tabular upload, formula sanitization, profiling, and separate imputation storage."""
    # CSV with formula injection, missing values, and numeric/categorical columns
    csv_content = (
        "name,score,formula_col\n"
        "Alice,95.5,=1+1\n"
        "Bob,,@SUM(A1:A2)\n"
        "Charlie,80.0,-cmd|' /C calc'!A0\n"
        "David,75.0,+12345\n"
        "Eve,,\n"
    )
    files = {"file": ("students.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    res = client.post("/upload", files=files)
    assert res.status_code == 200
    data = res.json()

    # 1. Check response metadata
    assert data["fileName"] == "students.csv"
    assert data["detectedKind"] == "tabular"
    assert data["detectedFormat"] == "csv"
    assert data["rowCount"] == 5
    assert data["columnCount"] == 3
    assert data["memoryUsageBytes"] > 0
    assert data["fileId"].startswith("f_")

    # 2. Check Raw Null Profile populated in appropriate field (not imputed data!)
    raw_profile = data["rawNullProfile"]
    assert raw_profile is not None
    assert "score" in raw_profile
    assert raw_profile["score"]["nullCount"] == 2
    assert raw_profile["score"]["nullPercentage"] == 40.0
    assert raw_profile["name"]["nullCount"] == 0

    # 3. Check DATA_STORE stores raw profile and imputed modeling data separately
    file_id = data["fileId"]
    assert file_id in DATA_STORE
    stored = DATA_STORE[file_id]

    raw_df = stored["raw_dataframe"]
    imputed_df = stored["imputed_modeling_data"]

    # Raw DataFrame has NaNs and sanitized formula injection prefixes
    assert raw_df["score"].isna().sum() == 2
    # Check formula prefixes neutralized with single quote prefix
    assert raw_df["formula_col"].iloc[0].startswith("'=")
    assert raw_df["formula_col"].iloc[1].startswith("'@")

    # Imputed DataFrame has 0 NaNs in numeric columns and was-missing indicator
    assert imputed_df["score"].isna().sum() == 0
    assert "score_was_missing" in imputed_df.columns


def test_upload_document_pdf_success(client, sample_pdf_bytes):
    """Test successful document parsing through /upload."""
    files = {"file": ("report.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
    res = client.post("/upload", files=files)
    assert res.status_code == 200
    data = res.json()

    assert data["fileName"] == "report.pdf"
    assert data["detectedKind"] == "document"
    assert data["detectedFormat"] == "pdf"
    assert data["rowCount"] >= 1
    assert data["columnCount"] is None
    assert data["columns"] is None
    assert data["rawNullProfile"] is None


def test_upload_invalid_mime_fails_with_400(client):
    """Test MIME disagreement or invalid MIME returns HTTP 400 with clear error."""
    # CSV file with PDF MIME type (MIME / extension disagreement)
    files = {"file": ("data.csv", io.BytesIO(b"a,b,c\n1,2,3"), "application/pdf")}
    res = client.post("/upload", files=files)
    assert res.status_code == 400
    assert "disagrees with file extension" in res.json()["detail"]


def test_upload_empty_file_fails_with_400(client):
    """Test empty file returns HTTP 400 with clear error."""
    files = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
    res = client.post("/upload", files=files)
    assert res.status_code == 400
    assert "Empty file" in res.json()["detail"]


def test_upload_oversized_file_fails_with_400(client):
    """Test file exceeding MAX_FILE_SIZE_MB returns HTTP 400 with clear error."""
    # 51 MB > 50 MB
    large_bytes = b"0" * (51 * 1024 * 1024)
    files = {"file": ("huge.csv", io.BytesIO(large_bytes), "text/csv")}
    res = client.post("/upload", files=files)
    assert res.status_code == 400
    assert "File exceeds" in res.json()["detail"]
