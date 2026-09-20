"""CORS Preflight & Origin Configuration Verification Test Suite."""

import pytest
from starlette.testclient import TestClient

from config.settings import settings
from main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_cors_preflight_on_analytics_endpoints(client):
    """Verify CORS preflight OPTIONS request returns 200 with allowed origin and credentials."""
    origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    endpoints = ["/api/v1/forecast", "/api/v1/hypotheses", "/upload"]

    for endpoint in endpoints:
        for origin in origins:
            headers = {
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            }
            res = client.options(endpoint, headers=headers)
            assert res.status_code == 200, f"Expected 200 for OPTIONS on {endpoint} from {origin}"
            assert res.headers.get("access-control-allow-origin") == origin
            assert res.headers.get("access-control-allow-credentials") == "true"


def test_cors_disallows_unapproved_origins(client):
    """Verify CORS headers omit Access-Control-Allow-Origin for untrusted origins."""
    headers = {
        "Origin": "http://malicious-external-origin.com",
        "Access-Control-Request-Method": "POST",
    }
    res = client.options("/api/v1/forecast", headers=headers)
    assert res.headers.get("access-control-allow-origin") is None
