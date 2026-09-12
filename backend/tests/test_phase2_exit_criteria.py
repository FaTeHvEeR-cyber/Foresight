"""Phase 2 Exit Criteria Verification Test Suite.

Verifies the concrete pass/fail exit criteria for Phase 2:
1. A file with a disallowed extension is rejected (400)
2. A file with a mismatched MIME type vs. extension is rejected (400)
3. A file over 50MB is rejected (400), a file under is accepted (200)
4. A tabular file with nulls returns BOTH an accurate raw null profile AND
   successfully imputed data ready for modeling — confirming these are NOT the same values
5. ENABLE_RATE_LIMITING=False means no request is throttled during tests
6. Validate strict contract compliance against frontend/types/api.ts UploadResponse
"""

import io
import pytest
from starlette.testclient import TestClient
import pandas as pd
import numpy as np

from config.settings import settings
from main import app, DATA_STORE


@pytest.fixture
def client():
    return TestClient(app)


def test_1_disallowed_extension_rejected(client):
    """Exit Criterion 1: A file with a disallowed extension is rejected with HTTP 400."""
    disallowed_files = [
        ("malware.exe", b"MZ\x90\x00executable", "application/octet-stream"),
        ("exploit.py", b"import os; os.system('ls')", "text/x-python"),
        ("archive.zip", b"PK\x03\x04ziparchive", "application/zip"),
        ("binary.bin", b"\x00\x01\x02\x03", "application/octet-stream"),
        ("page.html", b"<html><body>hello</body></html>", "text/html"),
    ]

    for filename, content, mime in disallowed_files:
        files = {"file": (filename, io.BytesIO(content), mime)}
        res = client.post("/upload", files=files)
        assert res.status_code == 400, f"Expected 400 for {filename}, got {res.status_code}: {res.text}"
        detail = res.json()["detail"].lower()
        assert "unsupported file extension" in detail or "disallowed" in detail or "extension" in detail


def test_2_mismatched_mime_type_vs_extension_rejected(client):
    """Exit Criterion 2: A file with a mismatched MIME type vs. extension is rejected with HTTP 400."""
    mismatched_pairs = [
        # CSV with PDF MIME type
        ("dataset.csv", b"a,b,c\n1,2,3", "application/pdf"),
        # PDF with CSV MIME type
        ("dossier.pdf", b"%PDF-1.4\nsome content", "text/csv"),
        # Plain text with Excel MIME type
        ("notes.txt", b"plain text content", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        # XLSX with plain text MIME type
        ("sheet.xlsx", b"PK\x03\x04openxml", "text/plain"),
    ]

    for filename, content, mime in mismatched_pairs:
        files = {"file": (filename, io.BytesIO(content), mime)}
        res = client.post("/upload", files=files)
        assert res.status_code == 400, f"Expected 400 for mismatched {filename} with {mime}, got {res.status_code}"
        detail = res.json()["detail"].lower()
        assert "disagrees with file extension" in detail or "unsupported" in detail


def test_3_file_size_limits_over_and_under_50mb(client):
    """Exit Criterion 3: A file over 50MB is rejected (400), a file under is accepted (200)."""
    # 1. File strictly over 50MB: 50MB + 1024 bytes -> rejected with 400
    oversized_size = 50 * 1024 * 1024 + 1024
    oversized_bytes = b"0" * oversized_size
    files_oversized = {"file": ("large_data.csv", io.BytesIO(oversized_bytes), "text/csv")}
    res_oversized = client.post("/upload", files=files_oversized)
    assert res_oversized.status_code == 400
    detail = res_oversized.json()["detail"].lower()
    assert "exceeds" in detail and "50mb" in detail

    # 2. File under 50MB: valid CSV payload -> accepted with 200
    valid_csv = b"metric,value\nalpha,10.5\nbeta,20.2\n"
    files_valid = {"file": ("under_limit.csv", io.BytesIO(valid_csv), "text/csv")}
    res_valid = client.post("/upload", files=files_valid)
    assert res_valid.status_code == 200
    data = res_valid.json()
    assert data["fileName"] == "under_limit.csv"
    assert data["rowCount"] == 2
    assert data["columnCount"] == 2


def test_4_dual_output_raw_null_profile_vs_imputed_modeling_data(client):
    """Exit Criterion 4: Tabular file with nulls returns BOTH an accurate raw null profile

    AND successfully imputed data ready for modeling — confirming these are NOT the same values.
    """
    # Create tabular CSV with deliberate nulls in numeric and categorical columns
    # age: [20.0, NaN, 30.0, NaN, 40.0] -> 2 nulls out of 5 (40.0%), median is 30.0
    # salary: [50000.0, 60000.0, NaN, 80000.0, 90000.0] -> 1 null out of 5 (20.0%), median is 70000.0
    # department: ["Eng", None, "Sales", "Eng", "HR"] -> 1 null out of 5 (20.0%)
    # score: [10.0, 20.0, 30.0, 40.0, 50.0] -> 0 nulls out of 5 (0.0%)
    csv_text = (
        "age,salary,department,score\n"
        "20.0,50000.0,Eng,10.0\n"
        ",60000.0,,20.0\n"
        "30.0,,Sales,30.0\n"
        ",80000.0,Eng,40.0\n"
        "40.0,90000.0,HR,50.0\n"
    )
    files = {"file": ("null_profile_test.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")}
    res = client.post("/upload", files=files)
    assert res.status_code == 200
    data = res.json()

    file_id = data["fileId"]

    # 1. Verify accurate raw null profile in response
    raw_profile = data["rawNullProfile"]
    assert raw_profile is not None, "rawNullProfile must be populated in UploadResponse"

    # Verify per-column raw null metrics
    assert raw_profile["age"]["nullCount"] == 2
    assert raw_profile["age"]["nullPercentage"] == 40.0
    assert raw_profile["age"]["totalRows"] == 5

    assert raw_profile["salary"]["nullCount"] == 1
    assert raw_profile["salary"]["nullPercentage"] == 20.0
    assert raw_profile["salary"]["totalRows"] == 5

    assert raw_profile["department"]["nullCount"] == 1
    assert raw_profile["department"]["nullPercentage"] == 20.0
    assert raw_profile["department"]["totalRows"] == 5

    assert raw_profile["score"]["nullCount"] == 0
    assert raw_profile["score"]["nullPercentage"] == 0.0
    assert raw_profile["score"]["totalRows"] == 5

    # Also verify column descriptors retain raw null counts
    col_map = {c["name"]: c for c in data["columns"]}
    assert col_map["age"]["nullCount"] == 2
    assert col_map["salary"]["nullCount"] == 1
    assert col_map["department"]["nullCount"] == 1
    assert col_map["score"]["nullCount"] == 0

    # 2. Retrieve the separately stored raw DataFrame and imputed modeling data
    assert file_id in DATA_STORE, "Dataset must be stored in DATA_STORE"
    stored = DATA_STORE[file_id]
    raw_df: pd.DataFrame = stored["raw_dataframe"]
    imputed_df: pd.DataFrame = stored["imputed_modeling_data"]

    # 3. Confirm these are NOT the same values (raw vs imputed divergence):
    # Raw data MUST retain NaNs
    assert raw_df["age"].isna().sum() == 2, "Raw data lost its nulls!"
    assert raw_df["salary"].isna().sum() == 1, "Raw data lost its nulls!"
    assert raw_df["department"].isna().sum() == 1, "Raw data lost its nulls!"

    # Imputed modeling data MUST have 0 NaNs in numeric columns
    assert imputed_df["age"].isna().sum() == 0, "Imputed data still contains NaNs in 'age'!"
    assert imputed_df["salary"].isna().sum() == 0, "Imputed data still contains NaNs in 'salary'!"
    assert imputed_df["score"].isna().sum() == 0, "Imputed data has NaNs in 'score'!"

    # Imputed values must equal the median (not NaN)
    # Median of [20.0, 30.0, 40.0] is 30.0
    assert imputed_df.loc[1, "age"] == 30.0
    assert imputed_df.loc[3, "age"] == 30.0
    # Median of [50000.0, 60000.0, 80000.0, 90000.0] is 70000.0
    assert imputed_df.loc[2, "salary"] == 70000.0

    # Imputed data must contain missing indicator features
    assert "age_was_missing" in imputed_df.columns
    assert "salary_was_missing" in imputed_df.columns
    assert "score_was_missing" not in imputed_df.columns  # Had 0 nulls

    # Confirm raw profile null counts differ completely from imputed modeling data null counts
    assert raw_df["age"].isna().sum() != imputed_df["age"].isna().sum()
    assert raw_df["salary"].isna().sum() != imputed_df["salary"].isna().sum()
    assert pd.isna(raw_df.loc[1, "age"])
    assert not pd.isna(imputed_df.loc[1, "age"])


def test_5_rate_limiting_inert_when_disabled(client):
    """Exit Criterion 5: ENABLE_RATE_LIMITING=False means no request is throttled during tests."""
    assert settings.ENABLE_RATE_LIMITING is False

    # Send 60 consecutive requests rapidly to verify zero throttling
    for i in range(60):
        res = client.get("/health")
        assert res.status_code == 200, f"Request {i+1} was unexpectedly throttled: {res.status_code}"


def test_6_upload_response_contract_compliance(client):
    """Verify strict contract compliance with frontend types/api.ts UploadResponse schema."""
    valid_csv = (
        "transaction_id,amount,status,notes\n"
        "TX101,150.75,completed,verified\n"
        "TX102,89.50,pending,\n"
        "TX103,45.00,completed,verified\n"
    )
    files = {"file": ("transactions.csv", io.BytesIO(valid_csv.encode("utf-8")), "text/csv")}
    res = client.post("/upload", files=files)
    assert res.status_code == 200
    data = res.json()

    # Required contract fields from frontend/types/api.ts
    # 1. fileId: string
    assert isinstance(data["fileId"], str) and len(data["fileId"]) > 0

    # 2. fileName: string
    assert data["fileName"] == "transactions.csv"

    # 3. fileSizeBytes: number
    assert isinstance(data["fileSizeBytes"], int) and data["fileSizeBytes"] > 0

    # 4. detectedKind: "tabular" | "document" | "mixed"
    assert data["detectedKind"] in {"tabular", "document", "mixed"}
    assert data["detectedKind"] == "tabular"

    # 5. detectedFormat: "csv" | "tsv" | "xlsx" | "xls" | "parquet" | "pdf" | "docx" | "txt" | "md"
    assert data["detectedFormat"] in {"csv", "tsv", "xlsx", "xls", "parquet", "pdf", "docx", "txt", "md"}
    assert data["detectedFormat"] == "csv"

    # 6. rowCount?: number
    assert isinstance(data["rowCount"], int)
    assert data["rowCount"] == 3

    # 7. columnCount?: number
    assert isinstance(data["columnCount"], int)
    assert data["columnCount"] == 4

    # 8. columns?: ColumnDescriptor[]
    assert isinstance(data["columns"], list)
    assert len(data["columns"]) == 4
    for col in data["columns"]:
        assert isinstance(col["name"], str)
        assert col["inferredType"] in {"numeric", "categorical", "datetime", "text", "boolean"}
        assert isinstance(col["nullCount"], int)
        if "nullPercentage" in col and col["nullPercentage"] is not None:
            assert isinstance(col["nullPercentage"], (int, float))

    # 9. rawNullProfile?: Record<string, ColumnNullProfile>
    assert isinstance(data["rawNullProfile"], dict)
    for col_name, null_prof in data["rawNullProfile"].items():
        assert isinstance(col_name, str)
        assert isinstance(null_prof["nullCount"], int)
        assert isinstance(null_prof["nullPercentage"], (int, float))
        assert isinstance(null_prof["totalRows"], int)

    # 10. memoryUsageBytes: number
    assert isinstance(data["memoryUsageBytes"], int) and data["memoryUsageBytes"] > 0
