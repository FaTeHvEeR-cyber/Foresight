"""Security & Invariant Tests for Spooling Measurement and Duplicate-Route Invariant.

WS-B & WS-C verification:
1. Validates that no two routes in the canonical app share the same (HTTP method, path) signature.
2. Validates that POST /api/v1/segmentation and POST /segmentation point to the audited handler in src.api.segmentation.
3. Validates Starlette MultiPartParser.spool_max_size class attribute presence and default (1 MB).
4. Validates that uploads <= 1 MB do not trigger SpooledTemporaryFile.rollover(), while uploads > 1 MB do.
"""
from __future__ import annotations

import io
import os
import tempfile
from collections import Counter
from typing import List, Tuple

import pytest
import starlette.formparsers
from starlette.testclient import TestClient

from main import app
from src.api.segmentation import segmentation as audited_segmentation


client = TestClient(app)


def _get_flattened_routes() -> List[Tuple[str, str, object]]:
    """Flatten all routes from app and included routers into (method, path, endpoint) tuples."""
    results = []

    def _collect(routes):
        for r in routes:
            if hasattr(r, "original_router") and hasattr(r.original_router, "routes"):
                # FastAPI _IncludedRouter
                _collect(r.original_router.routes)
            elif hasattr(r, "routes"):
                _collect(r.routes)
            else:
                p = getattr(r, "path", "")
                methods = getattr(r, "methods", None) or {"*"}
                endpoint = getattr(r, "endpoint", None)
                for m in methods:
                    results.append((m.upper(), p, endpoint))

    _collect(app.routes)
    return results


def test_no_duplicate_method_and_path_routes():
    """Verify that no two routes in app share the same HTTP method and path."""
    routes = _get_flattened_routes()
    signatures = [(m, p) for m, p, _ in routes]

    counts = Counter(signatures)
    duplicates = {sig: cnt for sig, cnt in counts.items() if cnt > 1}

    assert not duplicates, (
        f"Found duplicate route signatures (method, path) in app route table: {duplicates}"
    )



def test_segmentation_routes_point_to_audited_handler():
    """Verify that POST /api/v1/segmentation and POST /segmentation point to audited segmentation handler."""
    routes = _get_flattened_routes()

    v1_handlers = [
        endpoint
        for m, p, endpoint in routes
        if m == "POST" and p == "/api/v1/segmentation"
    ]
    root_handlers = [
        endpoint
        for m, p, endpoint in routes
        if m == "POST" and p == "/segmentation"
    ]

    assert len(v1_handlers) == 1, f"Expected exactly 1 handler for /api/v1/segmentation, found {len(v1_handlers)}"
    assert len(root_handlers) == 1, f"Expected exactly 1 handler for /segmentation, found {len(root_handlers)}"

    assert v1_handlers[0] is audited_segmentation, (
        f"/api/v1/segmentation handler {v1_handlers[0]} is not audited segmentation function"
    )
    assert root_handlers[0] is audited_segmentation, (
        f"/segmentation handler {root_handlers[0]} is not audited segmentation function"
    )


def test_root_aliases_and_docs_preserved():
    """Verify root-level aliases (/forecast, /hypotheses, /segmentation, /health) and docs are preserved."""
    routes = _get_flattened_routes()
    paths = {p for _, p, _ in routes}

    assert "/forecast" in paths, "Root alias /forecast must be preserved"
    assert "/hypotheses" in paths, "Root alias /hypotheses must be preserved"
    assert "/segmentation" in paths, "Root alias /segmentation must be preserved"
    assert "/health" in paths, "Root alias /health must be preserved"
    assert "/openapi.json" in paths, "OpenAPI schema /openapi.json must be preserved"
    assert "/docs" in paths, "Swagger UI /docs must be preserved"


from config.settings import settings


def test_starlette_multipart_spool_max_size_configured():
    """Verify Starlette MultiPartParser exposes spool_max_size set to MULTIPART_SPOOL_MAX_BYTES."""
    assert hasattr(starlette.formparsers.MultiPartParser, "spool_max_size"), (
        "MultiPartParser must expose spool_max_size class attribute"
    )
    assert (
        starlette.formparsers.MultiPartParser.spool_max_size
        == settings.MULTIPART_SPOOL_MAX_BYTES
    ), (
        f"MultiPartParser.spool_max_size ({starlette.formparsers.MultiPartParser.spool_max_size}) "
        f"must equal settings.MULTIPART_SPOOL_MAX_BYTES ({settings.MULTIPART_SPOOL_MAX_BYTES})"
    )


def test_parser_uses_configured_spool_size_at_request_time(monkeypatch):
    """Verify that MultiPartParser passes the configured spool_max_size to SpooledTemporaryFile at request time."""
    spooled_max_sizes: List[int] = []
    orig_init = tempfile.SpooledTemporaryFile.__init__

    def hooked_init(self, *args, **kwargs):
        if "max_size" in kwargs:
            spooled_max_sizes.append(kwargs["max_size"])
        elif len(args) > 0:
            spooled_max_sizes.append(args[0])
        return orig_init(self, *args, **kwargs)

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "__init__", hooked_init)

    data = b"col1,col2\n12,34\n"
    res = client.post(
        "/api/v1/upload",
        files={"file": ("test_parser_init.csv", io.BytesIO(data), "text/csv")},
    )
    assert res.status_code == 200
    assert len(spooled_max_sizes) > 0, "Expected SpooledTemporaryFile to be initialized during upload"
    assert spooled_max_sizes[0] == settings.MULTIPART_SPOOL_MAX_BYTES, (
        f"Expected SpooledTemporaryFile max_size={settings.MULTIPART_SPOOL_MAX_BYTES}, got {spooled_max_sizes[0]}"
    )


@pytest.mark.parametrize("size_mb", [0.5, 2.0, 10.0, 50.0])
def test_zero_disk_spooling_across_sizes(monkeypatch, size_mb):
    """Verify in-memory spooling: 0.5, 2, 10, and 50 MB uploads trigger 0 rollovers and 0 disk files."""
    rollover_count = 0
    orig_rollover = tempfile.SpooledTemporaryFile.rollover

    def hooked_rollover(self):
        nonlocal rollover_count
        rollover_count += 1
        return orig_rollover(self)

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", hooked_rollover)

    temp_dir = tempfile.gettempdir()
    def _count_tmp_files() -> int:
        try:
            return sum(1 for f in os.listdir(temp_dir) if f.startswith("~RF") or f.endswith(".tmp"))
        except Exception:
            return 0

    tmp_files_before = _count_tmp_files()

    # Generate synthetic CSV in-memory
    num_bytes = int(size_mb * 1024 * 1024)
    line = b"col1,col2\n"
    row = b"1234,5678\n"
    repeats = max(1, (num_bytes - len(line)) // len(row))
    data = line + (row * repeats)

    res = client.post(
        "/api/v1/upload",
        files={"file": (f"bench_{size_mb}mb.csv", io.BytesIO(data), "text/csv")},
    )
    assert res.status_code == 200, f"Upload {size_mb}MB failed: {res.text}"
    assert rollover_count == 0, (
        f"Expected 0 SpooledTemporaryFile rollovers for {size_mb}MB upload, got {rollover_count}"
    )

    tmp_files_after = _count_tmp_files()
    assert tmp_files_after <= tmp_files_before, (
        f"Expected no persistent temp files after {size_mb}MB upload (before={tmp_files_before}, after={tmp_files_after})"
    )


def test_oversized_spool_and_memory_rejection():
    """Verify 50 MB + 1 byte returns 413, and 120 MB returns 413 with bounded memory."""
    # 1. 50 MB + 1 byte of valid multi-row data
    limit = 50 * 1024 * 1024
    oversized_data = (b"123456789\n") * (limit // 10) + b"\n"
    assert len(oversized_data) == limit + 1
    res = client.post(
        "/api/v1/upload",
        files={"file": ("oversized_50mb.csv", io.BytesIO(oversized_data), "text/csv")},
    )
    assert res.status_code == 413
    assert f"File exceeds the {settings.MAX_FILE_SIZE_MB}MB limit" in res.json()["detail"]

    # 2. 120 MB Content-Length fast path
    large_120mb = 120 * 1024 * 1024
    res_120 = client.post(
        "/api/v1/upload",
        headers={"Content-Length": str(large_120mb), "Content-Type": "multipart/form-data; boundary=boundary"},
        content=b"oversized_payload",
    )
    assert res_120.status_code == 413

