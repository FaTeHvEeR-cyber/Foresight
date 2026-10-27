"""Security & Invariant Tests for Spooling Measurement and Duplicate-Route Invariant.

WS-B & WS-C verification:
1. Validates that no two routes in the canonical app share the same (HTTP method, path) signature.
2. Validates that POST /api/v1/segmentation and POST /segmentation point to the audited handler in src.api.segmentation.
3. Validates Starlette MultiPartParser.spool_max_size class attribute presence and default (1 MB).
4. Validates that uploads <= 1 MB do not trigger SpooledTemporaryFile.rollover(), while uploads > 1 MB do.
"""
from __future__ import annotations

import io
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


def test_starlette_multipart_spool_max_size_class_attribute():
    """Verify Starlette MultiPartParser exposes spool_max_size attribute with 1 MB default."""
    assert hasattr(starlette.formparsers.MultiPartParser, "spool_max_size"), (
        "MultiPartParser must expose spool_max_size class attribute"
    )
    assert starlette.formparsers.MultiPartParser.spool_max_size == 1024 * 1024, (
        f"Default spool_max_size must be 1 MB (1048576 bytes), got {starlette.formparsers.MultiPartParser.spool_max_size}"
    )


def test_spooling_rollover_threshold(monkeypatch):
    """Verify upload rollover mechanics: <= 1MB does not trigger rollover, > 1MB triggers rollover."""
    rollover_count = 0
    orig_rollover = tempfile.SpooledTemporaryFile.rollover

    def hooked_rollover(self):
        nonlocal rollover_count
        rollover_count += 1
        return orig_rollover(self)

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", hooked_rollover)

    # 1. 0.5 MB upload (512 KB <= 1 MB): 0 rollovers
    rollover_count = 0
    small_data = b"col1,col2\n" + (b"12,34\n" * 50_000)  # ~300 KB
    res_small = client.post(
        "/api/v1/upload",
        files={"file": ("small.csv", io.BytesIO(small_data), "text/csv")},
    )
    assert res_small.status_code == 200
    assert rollover_count == 0, f"Expected 0 rollovers for small upload, got {rollover_count}"

    # 2. 2 MB upload (> 1 MB default spool): triggers rollover
    rollover_count = 0
    num_bytes = 2 * 1024 * 1024
    line = b"col1,col2\n"
    row = b"1234,5678\n"
    repeats = (num_bytes - len(line)) // len(row)
    large_data = line + (row * repeats)
    res_large = client.post(
        "/api/v1/upload",
        files={"file": ("large_2mb.csv", io.BytesIO(large_data), "text/csv")},
    )
    assert res_large.status_code == 200
    assert rollover_count == 1, f"Expected 1 rollover for 2MB upload under default 1MB spool, got {rollover_count}"
