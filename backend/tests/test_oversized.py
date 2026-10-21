"""Tests for the 50MB file size guardrail and 10MB single-field limit."""

import io
import pytest
from fastapi import status
from config.settings import settings
from src.parsers.sanitization import FileSizeError, validate_file_size


def test_oversized_file_rejected():
    """Verify that any file strictly exceeding 50MB raises HTTP 413 FileSizeError."""
    oversized_bytes = settings.UPLOAD_MAX_SIZE_BYTES + 1
    with pytest.raises(FileSizeError) as exc:
        validate_file_size(oversized_bytes)
    assert exc.value.status_code == 413
    assert f"File exceeds the {settings.MAX_FILE_SIZE_MB}MB limit" in exc.value.detail


def test_boundary_file_accepted():
    """Verify that files at or just below 50MB pass size validation."""
    exact_limit = settings.UPLOAD_MAX_SIZE_BYTES
    validate_file_size(exact_limit)

    under_limit = settings.UPLOAD_MAX_SIZE_BYTES - 1024
    validate_file_size(under_limit)


def test_api_rejects_oversized_upload(client):
    """Test endpoint rejects oversized upload (50MB + 1 byte of normal multi-row data) with HTTP 413."""
    # Multi-row CSV where each row is short (10 bytes) so it does NOT trip the 10MB single-field guard
    # 5,242,880 rows * 10 bytes = 52,428,800 bytes (exactly 50 MB) + 1 newline byte = 52,428,801 bytes (> 50 MB)
    limit = 50 * 1024 * 1024
    oversized_data = (b"123456789\n") * (limit // 10) + b"\n"
    assert len(oversized_data) == limit + 1

    response = client.post(
        "/api/v1/upload",
        files={"file": ("large_multi_row.csv", io.BytesIO(oversized_data), "text/csv")},
    )
    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    assert f"File exceeds the {settings.MAX_FILE_SIZE_MB}MB limit" in response.json()["detail"]


def test_api_rejects_single_field_exceeding_10mb(client):
    """Test endpoint rejects a single field/row exceeding 10MB with HTTP 413."""
    # Under 50MB total file size (11MB total), but a single field exceeds 10MB
    field_data = b"col1,col2\nval1," + (b"A" * (10 * 1024 * 1024 + 10)) + b"\n"
    response = client.post(
        "/api/v1/upload",
        files={"file": ("large_field.csv", io.BytesIO(field_data), "text/csv")},
    )
    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    detail = response.json()["detail"].lower()
    assert "single field" in detail and "exceeds" in detail
