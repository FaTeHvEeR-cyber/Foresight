"""Test suite for Phase 2 Exit Criteria: Security Gatekeeper.

Verifies:
1. Ingestion correctly rejects oversized files (>25MB).
2. Ingestion correctly rejects invalid MIME types and disallowed extensions.
3. Ingestion detects and rejects spoofed binary files (executables disguised as CSV/XLSX/PDF).
"""

import io
import pytest
from fastapi import status


def test_reject_oversized_file(client):
    """Exit Criteria: reject files exceeding 25MB hard guardrail with HTTP 413."""
    # 25MB + 1KB
    oversized_bytes = b"0" * (25 * 1024 * 1024 + 1024)
    files = {"file": ("huge_dataset.csv", io.BytesIO(oversized_bytes), "text/csv")}
    
    response = client.post("/api/upload", files=files)
    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert "25MB" in response.json()["detail"]


def test_reject_disallowed_extensions(client):
    """Exit Criteria: reject disallowed extensions (e.g. .exe, .py, .bin, .html) with HTTP 415."""
    disallowed_files = [
        ("malware.exe", b"binary content", "application/octet-stream"),
        ("script.py", b"print('exploit')", "text/x-python"),
        ("payload.sh", b"#!/bin/bash\nrm -rf /", "application/x-sh"),
        ("blob.bin", b"\x00\x01\x02\x03", "application/octet-stream"),
        ("index.html", b"<html><body>Hi</body></html>", "text/html"),
    ]

    for filename, content, mime in disallowed_files:
        files = {"file": (filename, io.BytesIO(content), mime)}
        response = client.post("/api/upload", files=files)
        assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, (
            f"Expected 415 for {filename}, got {response.status_code}"
        )
        assert "Unsupported file extension" in response.json()["detail"] or "disallowed" in response.json()["detail"]


def test_reject_spoofed_executable_as_csv(client):
    """Exit Criteria: reject Windows PE executable header (MZ) disguised as .csv."""
    fake_csv_pe = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"
    files = {"file": ("report.csv", io.BytesIO(fake_csv_pe), "text/csv")}
    
    response = client.post("/api/upload", files=files)
    assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert "Executable binaries" in response.json()["detail"]


def test_reject_spoofed_elf_executable_as_txt(client):
    """Exit Criteria: reject Linux ELF executable header disguised as .txt."""
    fake_txt_elf = b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    files = {"file": ("notes.txt", io.BytesIO(fake_txt_elf), "text/plain")}
    
    response = client.post("/api/upload", files=files)
    assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert "Executable binaries" in response.json()["detail"]


def test_reject_spoofed_binary_in_csv(client):
    """Exit Criteria: reject binary data containing null bytes disguised as .csv."""
    binary_content = b"col1,col2\nval1,\x00\x01\x02\x03\n"
    files = {"file": ("data.csv", io.BytesIO(binary_content), "text/csv")}
    
    response = client.post("/api/upload", files=files)
    assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert "Binary or malformed" in response.json()["detail"]


def test_reject_spoofed_pdf(client):
    """Exit Criteria: reject file claiming to be PDF without %PDF- magic bytes."""
    corrupted_pdf = b"NOT_A_PDF_HEADER_JUST_TEXT"
    files = {"file": ("dossier.pdf", io.BytesIO(corrupted_pdf), "application/pdf")}
    
    response = client.post("/api/upload", files=files)
    assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert "%PDF-" in response.json()["detail"]


def test_reject_spoofed_parquet(client):
    """Exit Criteria: reject file claiming to be Parquet without PAR1 magic bytes."""
    corrupted_parquet = b"CORRUPTED_PARQUET_NO_HEADER"
    files = {"file": ("data.parquet", io.BytesIO(corrupted_parquet), "application/octet-stream")}
    
    response = client.post("/api/upload", files=files)
    assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert "PAR1" in response.json()["detail"]


def test_reject_spoofed_xlsx(client):
    """Exit Criteria: reject file claiming to be XLSX without Office Open XML package structure."""
    fake_xlsx = b"PK\x03\x04not_a_valid_openxml_sheet"
    files = {"file": ("financials.xlsx", io.BytesIO(fake_xlsx), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    
    response = client.post("/api/upload", files=files)
    assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert "Office Open XML" in response.json()["detail"]


def test_reject_empty_file(client):
    """Reject 0-byte upload."""
    files = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
    response = client.post("/api/upload", files=files)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "empty" in response.json()["detail"].lower()


def test_reject_file_without_extension(client):
    """Reject files lacking an extension."""
    files = {"file": ("raw_data", io.BytesIO(b"a,b,c\n1,2,3"), "text/plain")}
    response = client.post("/api/upload", files=files)
    assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert "no extension" in response.json()["detail"].lower()
