"""Test suite for rate limiting middleware placeholder."""

from fastapi import status
from app.config import settings
from app.middleware.rate_limit import RateLimitMiddleware


def test_rate_limiting_inert_by_default(client):
    """
    Verify rate limiting is disabled by default in Phase 2
    (ENABLE_RATE_LIMITING = False) and allows burst requests without throttling.
    """
    assert settings.ENABLE_RATE_LIMITING is False

    for _ in range(50):
        res = client.get("/api/health")
        assert res.status_code == status.HTTP_200_OK


def test_rate_limiting_active_when_enabled(client, monkeypatch):
    """
    Verify rate limiting middleware triggers HTTP 429 when ENABLE_RATE_LIMITING is enabled.
    """
    monkeypatch.setattr(settings, "ENABLE_RATE_LIMITING", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_REQUESTS_PER_MINUTE", 5)

    # Find RateLimitMiddleware instance on the app to reset state
    for middleware in client.app.user_middleware:
        if middleware.cls == RateLimitMiddleware:
            pass

    # Send 5 permitted requests
    for _ in range(5):
        res = client.get("/api/health")
        assert res.status_code == status.HTTP_200_OK

    # 6th request exceeds limit
    exceeded_res = client.get("/api/health")
    assert exceeded_res.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "Rate limit exceeded" in exceeded_res.json()["detail"]
    assert "Retry-After" in exceeded_res.headers
