"""Tests for Security Gatekeeper: MIME validation and magic byte inspection."""

import pytest
from app.services.validator import (
    FileValidationError,
    validate_file_type_and_signatures,
)


def test_rejects_unsupported_extensions():
    """Rejects files with disallowed extensions (.exe, .py, .sh, .png, .zip)."""
    disallowed = ["virus.exe", "script.py", "run.sh", "photo.png", "archive.zip"]
    for fname in disallowed:
        with pytest.raises(FileValidationError) as exc:
            validate_file_type_and_signatures(fname, b"dummy content", "text/plain")
        assert exc.value.status_code == 415
        assert "Unsupported file format" in exc.value.detail


def test_rejects_executable_magic_signatures():
    """Rejects executable magic bytes even if the extension looks valid."""
    # 1. Windows PE / EXE disguised as CSV
    pe_bytes = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"
    with pytest.raises(FileValidationError) as exc:
        validate_file_type_and_signatures("report.csv", pe_bytes, "text/csv")
    assert exc.value.status_code == 415
    assert "Disallowed binary signature detected: Windows executable" in exc.value.detail

    # 2. Linux ELF binary disguised as TSV
    elf_bytes = b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    with pytest.raises(FileValidationError) as exc:
        validate_file_type_and_signatures("data.tsv", elf_bytes, "text/tab-separated-values")
    assert exc.value.status_code == 415
    assert "Disallowed binary signature detected: Linux ELF" in exc.value.detail

    # 3. Shell script disguised as text
    sh_bytes = b"#!/bin/bash\nrm -rf /"
    with pytest.raises(FileValidationError) as exc:
        validate_file_type_and_signatures("notes.txt", sh_bytes, "text/plain")
    assert exc.value.status_code == 415
    assert "Disallowed binary signature detected: Script / shell executable" in exc.value.detail

    # 4. PNG image disguised as CSV
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    with pytest.raises(FileValidationError) as exc:
        validate_file_type_and_signatures("metrics.csv", png_bytes, "text/csv")
    assert exc.value.status_code == 415
    assert "Disallowed binary signature detected: PNG image" in exc.value.detail


def test_rejects_spoofed_pdf():
    """Rejects a PDF file that does not start with %PDF- header."""
    fake_pdf = b"This is not a real PDF document."
    with pytest.raises(FileValidationError) as exc:
        validate_file_type_and_signatures("dossier.pdf", fake_pdf, "application/pdf")
    assert exc.value.status_code == 415
    assert "Missing %PDF- file signature" in exc.value.detail


def test_rejects_spoofed_parquet():
    """Rejects a Parquet file that does not have PAR1 magic bytes."""
    fake_parquet = b"PARQUET_TEXT_MOCK"
    with pytest.raises(FileValidationError) as exc:
        validate_file_type_and_signatures("data.parquet", fake_parquet, "application/octet-stream")
    assert exc.value.status_code == 415
    assert "Missing PAR1 magic byte signature" in exc.value.detail


def test_rejects_corrupted_xlsx_zip():
    """Rejects an XLSX file that is not a valid zip archive."""
    fake_xlsx = b"PK\x03\x04corrupted zip payload"
    with pytest.raises(FileValidationError) as exc:
        validate_file_type_and_signatures("sales.xlsx", fake_xlsx, "application/vnd.ms-excel")
    assert exc.value.status_code == 415
    assert "Invalid ZIP archive" in exc.value.detail


def test_rejects_csv_with_binary_null_bytes():
    """Rejects CSV containing null bytes indicating binary content."""
    binary_csv = b"col1,col2\nval1,\x00\x01\x02\x03"
    with pytest.raises(FileValidationError) as exc:
        validate_file_type_and_signatures("data.csv", binary_csv, "text/csv")
    assert exc.value.status_code == 415
    assert "Contains null byte binary data" in exc.value.detail


def test_accepts_valid_formats(sample_csv_bytes, sample_parquet_bytes, sample_pdf_bytes):
    """Accepts valid CSV, Parquet, and PDF formats."""
    kind, fmt = validate_file_type_and_signatures("data.csv", sample_csv_bytes, "text/csv")
    assert kind == "tabular"
    assert fmt == "csv"

    kind, fmt = validate_file_type_and_signatures("data.parquet", sample_parquet_bytes, "application/octet-stream")
    assert kind == "tabular"
    assert fmt == "parquet"

    kind, fmt = validate_file_type_and_signatures("doc.pdf", sample_pdf_bytes, "application/pdf")
    assert kind == "document"
    assert fmt == "pdf"
