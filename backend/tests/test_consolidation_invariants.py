"""Tests for Phase 4 backend consolidation invariants.

Verifies:
1. Canonical app contains POST /api/v1/upload in route table.
2. Route aliases /upload and /api/upload are eliminated (return HTTP 404).
3. Legacy backend/app directory and session_store are retired and not importable.
4. No second FastAPI application or session cache exists.
"""

import sys
import importlib
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from main import app


def test_route_table_canonical_upload():
    """Verify route table contains POST /api/v1/upload and does not contain legacy aliases."""
    routes = []
    for r in app.routes:
        if hasattr(r, "path"):
            routes.append(r.path)
        elif hasattr(r, "routes"):
            for sr in r.routes:
                if hasattr(sr, "path"):
                    routes.append(sr.path)
    assert "/api/v1/upload" in routes, "Canonical /api/v1/upload must be in app routes"
    assert "/upload" not in routes, "Legacy alias /upload must not be in app routes"
    assert "/api/upload" not in routes, "Legacy alias /api/upload must not be in app routes"


def test_legacy_upload_routes_return_404(client):
    """Verify legacy upload endpoints return HTTP 404 Not Found."""
    res_upload = client.post("/upload")
    assert res_upload.status_code == status.HTTP_404_NOT_FOUND

    res_api_upload = client.post("/api/upload")
    assert res_api_upload.status_code == status.HTTP_404_NOT_FOUND


def test_legacy_app_module_not_importable():
    """Verify legacy backend/app directory and its submodules cannot be imported."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app")

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.main")

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.services.session_store")


def test_zero_persistence_session_store_nonexistent():
    """Verify session_store does not exist in backend modules."""
    with pytest.raises((ModuleNotFoundError, ImportError)):
        from services.session_store import session_store  # type: ignore # noqa: F401
