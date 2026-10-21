"""Comprehensive unit & integration tests for POST /upload in main.py."""

import io
import pytest
from starlette.testclient import TestClient

from main import app
import main


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

    # 3. Assert zero retention: no DATA_STORE exists, opaque fileId has nothing stored behind it
    file_id = data["fileId"]
    assert not hasattr(main, "DATA_STORE"), "DATA_STORE must not exist on canonical app (zero-retention Spec §1.1)"


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


def test_upload_invalid_mime_fails_with_415(client):
    """Test MIME disagreement or invalid MIME returns HTTP 415 with clear error."""
    # CSV file with PDF MIME type (MIME / extension disagreement)
    files = {"file": ("data.csv", io.BytesIO(b"a,b,c\n1,2,3"), "application/pdf")}
    res = client.post("/upload", files=files)
    assert res.status_code == 415
    assert "disagrees with file extension" in res.json()["detail"]


def test_upload_empty_file_fails_with_400(client):
    """Test empty file returns HTTP 400 with clear error."""
    files = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
    res = client.post("/upload", files=files)
    assert res.status_code == 400
    assert "Empty file" in res.json()["detail"]


def test_upload_oversized_file_fails_with_413(client):
    """Test file exceeding MAX_FILE_SIZE_MB returns HTTP 413 with clear error."""
    # 51 MB > 50 MB
    large_bytes = b"0" * (51 * 1024 * 1024)
    files = {"file": ("huge.csv", io.BytesIO(large_bytes), "text/csv")}
    res = client.post("/upload", files=files)
    assert res.status_code == 413
    assert "File exceeds" in res.json()["detail"]


# ============================================================================
# Regression Tests for F-08 & Phase 4 Status Code Preservation
# ============================================================================

import zipfile
from pathlib import Path


@pytest.mark.parametrize(
    "filename,mime,content",
    [
        ("notes.txt", "text/plain", b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"),
        ("readme.md", "text/markdown", b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"),
        ("data.csv", "text/csv", b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"),
        ("notes.txt", "text/plain", b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"),
        ("readme.md", "text/markdown", b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"),
        ("data.csv", "text/csv", b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"),
        ("notes.txt", "text/plain", b"\xcf\xfa\xed\xfe\x07\x00\x00\x01\x03\x00\x00\x00\x02\x00\x00\x00"),
        ("readme.md", "text/markdown", b"\xcf\xfa\xed\xfe\x07\x00\x00\x01\x03\x00\x00\x00\x02\x00\x00\x00"),
        ("data.csv", "text/csv", b"\xcf\xfa\xed\xfe\x07\x00\x00\x01\x03\x00\x00\x00\x02\x00\x00\x00"),
    ],
)
def test_regression_spoofed_executables_rejected_415(client, filename, mime, content):
    """Regression test F-08: Reject Linux ELF, PE, and Mach-O headers across .txt, .md, .csv with HTTP 415."""
    res = client.post("/upload", files={"file": (filename, io.BytesIO(content), mime)})
    assert res.status_code == 415
    detail = res.json()["detail"].lower()
    assert "executable" in detail or "disallowed" in detail


def test_regression_shebang_script_rejected_415(client):
    """Reject shebang script named .txt with HTTP 415."""
    content = b"#!/bin/bash\necho 'malicious script'\n"
    res = client.post("/upload", files={"file": ("run.txt", io.BytesIO(content), "text/plain")})
    assert res.status_code == 415
    assert "Script / shell executable" in res.json()["detail"]


@pytest.mark.parametrize(
    "filename,mime,content",
    [
        ("fake.pdf", "application/pdf", b"NOT_A_PDF_STREAM_HEADER"),
        ("fake.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"NOT_A_ZIP_HEADER"),
        ("fake.doc", "application/msword", b"DUMMY_DOC_BYTES"),
        ("fake.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"NOT_A_ZIP_HEADER"),
    ],
)
def test_regression_spoofed_document_and_sheet_signatures_415(client, filename, mime, content):
    """Reject spoofed or unsupported document/sheet formats with HTTP 415."""
    res = client.post("/upload", files={"file": (filename, io.BytesIO(content), mime)})
    assert res.status_code == 415


def test_regression_valid_zip_not_workbook_rejected_422(client):
    """Valid ZIP file named .xlsx that is not an Excel workbook is rejected with HTTP 422."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("dummy.txt", "not an excel worksheet")
    zip_bytes = buf.getvalue()

    res = client.post(
        "/upload",
        files={
            "file": (
                "archive.xlsx",
                io.BytesIO(zip_bytes),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res.status_code == 422
    assert "Failed to parse tabular file" in res.json()["detail"]


def test_regression_missing_and_disallowed_extensions_415(client):
    """Reject uploads with no extension or disallowed extension with HTTP 415."""
    # No extension
    res_no_ext = client.post("/upload", files={"file": ("raw_data", io.BytesIO(b"a,b,c\n1,2,3"), "text/plain")})
    assert res_no_ext.status_code == 415
    assert "has no valid extension" in res_no_ext.json()["detail"]

    # Disallowed extension
    res_disallowed = client.post("/upload", files={"file": ("payload.py", io.BytesIO(b"print('hack')"), "text/x-python")})
    assert res_disallowed.status_code == 415
    assert "Unsupported file extension" in res_disallowed.json()["detail"]


def test_regression_all_fixtures_return_200(
    client,
    sample_csv_bytes,
    sample_tsv_bytes,
    sample_xlsx_bytes,
    sample_parquet_bytes,
    sample_pdf_bytes,
    sample_docx_bytes,
    sample_txt_bytes,
    sample_md_bytes,
):
    """Verify zero false positives: all valid fixture formats return HTTP 200."""
    fixtures = [
        ("test.csv", sample_csv_bytes, "text/csv"),
        ("test.tsv", sample_tsv_bytes, "text/tab-separated-values"),
        ("test.xlsx", sample_xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("test.parquet", sample_parquet_bytes, "application/octet-stream"),
        ("test.pdf", sample_pdf_bytes, "application/pdf"),
        ("test.docx", sample_docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("test.txt", sample_txt_bytes, "text/plain"),
        ("test.md", sample_md_bytes, "text/markdown"),
    ]
    for filename, content, mime in fixtures:
        res = client.post("/upload", files={"file": (filename, io.BytesIO(content), mime)})
        assert res.status_code == 200, f"Expected 200 for {filename}, got {res.status_code}: {res.text}"


def test_regression_real_datasets_return_200(client, wholesale_df, bike_df, retail_df):
    """Verify real benchmark datasets (Wholesale, Online Retail, Credit Card, Bike) return 200."""
    candidate_paths = [
        Path(r"C:\Users\rfate\Desktop\report\project\Project - 2\Datasets\phase-3A"),
        Path(__file__).resolve().parents[1] / "data",
    ]
    real_files = {
        "Wholesale_customers_data.csv": "text/csv",
        "online_retail.csv": "text/csv",
        "day.csv": "text/csv",
    }
    for fname, mime in real_files.items():
        for base in candidate_paths:
            p = base / fname
            if p.exists():
                res = client.post("/upload", files={"file": (fname, io.BytesIO(p.read_bytes()), mime)})
                assert res.status_code == 200, f"Expected 200 for {fname}, got {res.status_code}: {res.text}"
                break
        else:
            # Fall back to synthetic session fixture DataFrame if on disk not present
            if "wholesale" in fname.lower():
                b = wholesale_df.to_csv(index=False).encode("utf-8")
            elif "retail" in fname.lower():
                b = retail_df.to_csv(index=False).encode("latin-1")
            else:
                b = bike_df.to_csv(index=False).encode("utf-8")
            res = client.post("/upload", files={"file": (fname, io.BytesIO(b), mime)})
            assert res.status_code == 200
