"""Tests for the 25MB file size guardrail (Phase 2 exit criteria)."""

import pytest
from app.config import settings
from app.services.validator import FileValidationError, validate_file_size


def test_oversized_file_rejected():
    """Verify that any file strictly exceeding 25MB raises HTTP 413."""
    oversized_bytes = settings.MAX_FILE_SIZE_BYTES + 1
    with pytest.raises(FileValidationError) as exc:
        validate_file_size(oversized_bytes)
    assert exc.value.status_code == 413
    assert "File exceeds the 25MB limit" in exc.value.detail


def test_boundary_file_accepted():
    """Verify that files at or just below 25MB pass size validation."""
    exact_limit = settings.MAX_FILE_SIZE_BYTES
    # Should not raise
    validate_file_size(exact_limit)

    under_limit = settings.MAX_FILE_SIZE_BYTES - 1024
    validate_file_size(under_limit)


def test_api_rejects_oversized_upload(client):
    """Test endpoint rejects oversized upload with HTTP 413."""
    # Construct an oversized payload (25MB + 100KB)
    chunk = b"A" * (1024 * 1024)  # 1 MB
    oversized_data = chunk * 26     # 26 MB

    response = client.post(
        "/api/upload",
        files={"file": ("large_file.csv", oversized_data, "text/csv")},
    )
    assert response.status_code == 413
    assert "File exceeds the 25MB limit" in response.json()["detail"]
