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


def test_content_length_oversized_fast_path_handler_never_entered(client, monkeypatch):
    """Test Content-Length > MAX_INGRESS_BODY_BYTES fast path rejects before handler is entered."""
    import main
    from src.api import analytics_router, segmentation

    def boom(*args, **kwargs):
        raise AssertionError("Route handler should NEVER be entered for oversized Content-Length fast path!")

    monkeypatch.setattr(main, "upload", boom)
    monkeypatch.setattr(analytics_router, "forecast", boom)
    monkeypatch.setattr(analytics_router, "hypotheses", boom)
    monkeypatch.setattr(segmentation, "segmentation", boom)

    protected_endpoints = [
        "/api/v1/upload",
        "/api/v1/forecast",
        "/api/v1/hypotheses",
        "/api/v1/segmentation",
    ]

    for endpoint in protected_endpoints:
        response = client.post(
            endpoint,
            headers={
                "content-length": "500000000",
                "content-type": "multipart/form-data; boundary=----boundary123",
            },
            content=b"tiny payload",
        )
        assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE, f"Endpoint {endpoint} failed: {response.text}"
        detail = response.json().get("detail", "")
        assert f"File exceeds the {settings.MAX_FILE_SIZE_MB}MB limit" in detail


def test_chunked_body_above_limit_aborts_with_413(client):
    """Test chunked or absent Content-Length upload aborts with HTTP 413 once limit + allowance is exceeded."""
    chunk_size = 5 * 1024 * 1024  # 5 MB chunks
    total_chunks = (settings.MAX_INGRESS_BODY_BYTES // chunk_size) + 2  # strictly above limit + allowance
    chunks_yielded = 0

    def chunk_generator():
        nonlocal chunks_yielded
        boundary = b"----chunkboundary"
        yield b"--" + boundary + b"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"chunked.csv\"\r\nContent-Type: text/csv\r\n\r\n"
        chunks_yielded += 1
        for _ in range(total_chunks):
            chunks_yielded += 1
            yield b"1234,5678,9012\n" * (chunk_size // 15)
        yield b"\r\n--" + boundary + b"--\r\n"

    response = client.post(
        "/api/v1/upload",
        headers={"content-type": "multipart/form-data; boundary=----chunkboundary"},
        content=chunk_generator(),
    )
    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    assert f"File exceeds the {settings.MAX_FILE_SIZE_MB}MB limit" in response.json()["detail"]


def test_exactly_50mb_valid_csv_accepted(client):
    """Test that a valid CSV file of exactly 50 MB (52,428,800 bytes) returns HTTP 200."""
    limit = 50 * 1024 * 1024
    line = b"col1,col2\n"
    row = b"1234,5678\n"  # 10 bytes
    repeats = (limit - len(line)) // len(row)
    data = line + (row * repeats)
    pad = limit - len(data)
    if pad > 0:
        data += b"0" * (pad - 1) + b"\n"
    assert len(data) == limit

    response = client.post(
        "/api/v1/upload",
        files={"file": ("exact_50mb.csv", io.BytesIO(data), "text/csv")},
    )
    assert response.status_code == status.HTTP_200_OK
    res_data = response.json()
    assert res_data["rowCount"] > 0
    assert res_data["fileSizeBytes"] == limit


def test_120mb_body_fast_path_bounded_rss(client):
    """Test that a 120 MB body upload triggers fast-path 413 with bounded memory."""
    import ctypes
    from ctypes import wintypes

    def get_working_set_mb() -> float:
        try:
            class PMC(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]
            fn = ctypes.windll.psapi.GetProcessMemoryInfo
            fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
            fn.restype = wintypes.BOOL
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            if fn(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
                return pmc.WorkingSetSize / (1024 * 1024)
        except Exception:
            pass
        return 0.0

    size_120mb = 120 * 1024 * 1024
    line = b"col1,col2\n"
    row = b"1234,5678\n"
    repeats = (size_120mb - len(line)) // len(row)
    content_120mb = line + (row * repeats)

    import gc
    gc.collect()
    rss_before = get_working_set_mb()

    response = client.post(
        "/api/v1/upload",
        files={"file": ("large_120mb.csv", io.BytesIO(content_120mb), "text/csv")},
    )

    rss_after = get_working_set_mb()
    del content_120mb
    gc.collect()

    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    assert f"File exceeds the {settings.MAX_FILE_SIZE_MB}MB limit" in response.json()["detail"]
    if rss_before > 0 and rss_after > 0:
        rss_delta = rss_after - rss_before
        # Under fast-path early rejection, delta should be near 0 and strictly < 50 MB (far below earlier +243 MB)
        assert rss_delta < 50.0, f"Peak RSS grew by {rss_delta:.1f} MB (expected near 0 MB)"


def test_multipart_file_first_with_extra_fields(client):
    """Test multipart upload with file field first and extra form fields after it behaves normally."""
    import pandas as pd

    df = pd.DataFrame({
        "date": pd.date_range("2023-01-01", periods=60, freq="D").astype(str),
        "sales": [100 + i for i in range(60)],
    })
    csv_bytes = df.to_csv(index=False).encode("utf-8")

    # Send file first, extra form parameters after
    response = client.post(
        "/api/v1/forecast",
        files={"file": ("forecast_series.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={"target": "sales", "date_col": "date", "use_llm": "false"},
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["status"] == "ok"
    assert "forecast" in body

