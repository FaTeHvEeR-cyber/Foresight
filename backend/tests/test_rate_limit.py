"""Test suite for rate limiting middleware placeholder."""

from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from config.settings import settings
from src.middleware.rate_limit import RateLimitMiddleware


def _create_rate_limit_test_app() -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(RateLimitMiddleware)

    @test_app.get("/api/health")
    def health():
        return {"status": "healthy"}

    return test_app


def test_rate_limiting_inert_by_default():
    """Verify rate limiting is disabled by default in Phase 2

    (ENABLE_RATE_LIMITING = False) and allows burst requests without throttling.
    """
    assert settings.ENABLE_RATE_LIMITING is False
    test_client = TestClient(_create_rate_limit_test_app())

    for _ in range(50):
        res = test_client.get("/api/health")
        assert res.status_code == status.HTTP_200_OK


def test_rate_limiting_active_when_enabled(monkeypatch):
    """Verify rate limiting middleware triggers HTTP 429 when ENABLE_RATE_LIMITING is enabled."""
    monkeypatch.setattr(settings, "ENABLE_RATE_LIMITING", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_REQUESTS_PER_MINUTE", 5)

    test_client = TestClient(_create_rate_limit_test_app())

    # Send 5 permitted requests
    for _ in range(5):
        res = test_client.get("/api/health")
        assert res.status_code == status.HTTP_200_OK

    # 6th request exceeds limit
    exceeded_res = test_client.get("/api/health")
    assert exceeded_res.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "Rate limit exceeded" in exceeded_res.json()["detail"]
    assert "Retry-After" in exceeded_res.headers

