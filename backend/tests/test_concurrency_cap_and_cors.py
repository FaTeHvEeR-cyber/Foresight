"""Tests for Upload Concurrency Capping and CORS Header Preservation (Phase 4 Tasks 1c).

Verifies:
1. Concurrency cap of 1 with overlapping requests gives one 200 and one 503 with Retry-After: 5.
2. The slot is released on success, error, and client disconnect/cancellation.
3. Health check endpoints (/health, /api/health) are exempt from concurrency caps.
4. 413 (Payload Too Large) response from BodyLimitMiddleware carries Access-Control-Allow-Origin.
5. 503 (Service Unavailable) response from UploadConcurrencyMiddleware carries Access-Control-Allow-Origin and Retry-After.
6. Inert RateLimiterPlaceholderMiddleware passes and does not throttle requests.
"""
from __future__ import annotations

import asyncio
import io
import pytest
import httpx
from starlette.testclient import TestClient

from config.settings import settings
from main import app, RateLimiterPlaceholderMiddleware
from src.middleware.concurrency_cap import UploadConcurrencyMiddleware


client = TestClient(app)


def test_cors_on_413_body_limit():
    """Verify that HTTP 413 response from BodyLimitMiddleware carries Access-Control-Allow-Origin."""
    # Oversized Content-Length (> MAX_INGRESS_BODY_BYTES = 50MB + 64KB)
    oversized_length = 60 * 1024 * 1024
    res = client.post(
        "/api/v1/upload",
        headers={
            "Origin": "http://localhost:3000",
            "Content-Length": str(oversized_length),
            "Content-Type": "multipart/form-data; boundary=boundary",
        },
        content=b"oversized_payload",
    )
    assert res.status_code == 413
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_on_503_concurrency_cap(monkeypatch):
    """Verify that HTTP 503 response from UploadConcurrencyMiddleware carries Access-Control-Allow-Origin and Retry-After."""
    monkeypatch.setattr(settings, "MAX_CONCURRENT_UPLOADS", 0)
    res = client.post(
        "/api/v1/upload",
        headers={
            "Origin": "http://localhost:3000",
            "Content-Type": "multipart/form-data; boundary=boundary",
        },
        content=b"--boundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"test.csv\"\r\nContent-Type: text/csv\r\n\r\na,b\n1,2\n--boundary--\r\n",
    )
    assert res.status_code == 503
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert res.headers.get("retry-after") == "5"
    assert "Server is handling maximum concurrent" in res.json()["detail"]


def test_concurrency_cap_overlap_gives_200_and_503(monkeypatch):
    """Verify cap of 1 with two overlapping requests yields one 200 and one 503 with Retry-After: 5."""
    monkeypatch.setattr(settings, "MAX_CONCURRENT_UPLOADS", 1)

    async def _run():
        transport = httpx.ASGITransport(app=app)

        async def slow_stream():
            yield b"--boundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"test.csv\"\r\nContent-Type: text/csv\r\n\r\ncol1,col2\r\n"
            await asyncio.sleep(0.2)
            yield b"1,2\r\n--boundary--\r\n"

        headers = {
            "content-type": "multipart/form-data; boundary=boundary",
            "origin": "http://localhost:3000",
        }

        fast_body = (
            b"--boundary\r\n"
            b"Content-Disposition: form-data; name=\"file\"; filename=\"fast.csv\"\r\n"
            b"Content-Type: text/csv\r\n\r\n"
            b"a,b\r\n1,2\r\n--boundary--\r\n"
        )

        async def worker_1():
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
                return await c.post("/api/v1/upload", content=slow_stream(), headers=headers)

        async def worker_2():
            await asyncio.sleep(0.04)  # Ensure worker 1 has acquired the slot
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
                return await c.post("/api/v1/upload", content=fast_body, headers=headers)

        res1, res2 = await asyncio.gather(worker_1(), worker_2())

        statuses = [res1.status_code, res2.status_code]
        assert 200 in statuses, f"Expected one 200 response, got {statuses}"
        assert 503 in statuses, f"Expected one 503 response, got {statuses}"

        resp_503 = res2 if res2.status_code == 503 else res1
        assert resp_503.headers.get("retry-after") == "5"
        assert resp_503.headers.get("access-control-allow-origin") == "http://localhost:3000"

    asyncio.run(_run())


def test_slot_released_on_success():
    """Verify that slot is released after successful request completion."""
    async def _run():
        async def inner_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = UploadConcurrencyMiddleware(inner_app, max_concurrent=1)
        assert middleware.active_count == 0

        scope = {"type": "http", "method": "POST", "path": "/api/v1/upload"}
        messages = []
        async def fake_send(msg): messages.append(msg)
        async def fake_receive(): return {"type": "http.request", "body": b""}

        await middleware(scope, fake_receive, fake_send)
        assert middleware.active_count == 0
        assert messages[0]["status"] == 200

    asyncio.run(_run())


def test_slot_released_on_exception():
    """Verify that slot is released when inner app raises an exception."""
    async def _run():
        async def failing_app(scope, receive, send):
            raise RuntimeError("Handler failure simulation")

        middleware = UploadConcurrencyMiddleware(failing_app, max_concurrent=1)
        assert middleware.active_count == 0

        scope = {"type": "http", "method": "POST", "path": "/api/v1/upload"}
        async def fake_send(msg): pass
        async def fake_receive(): return {"type": "http.request", "body": b""}

        with pytest.raises(RuntimeError, match="Handler failure simulation"):
            await middleware(scope, fake_receive, fake_send)

        assert middleware.active_count == 0, "Slot must be released even after an exception"

    asyncio.run(_run())


def test_slot_released_on_client_abort():
    """Verify that slot is released when client disconnects or task is cancelled."""
    async def _run():
        async def cancelled_app(scope, receive, send):
            raise asyncio.CancelledError()

        middleware = UploadConcurrencyMiddleware(cancelled_app, max_concurrent=1)
        assert middleware.active_count == 0

        scope = {"type": "http", "method": "POST", "path": "/api/v1/upload"}
        async def fake_send(msg): pass
        async def fake_receive(): return {"type": "http.request", "body": b""}

        with pytest.raises(asyncio.CancelledError):
            await middleware(scope, fake_receive, fake_send)

        assert middleware.active_count == 0, "Slot must be released after client abort/cancellation"

    asyncio.run(_run())


def test_health_check_exempt_from_concurrency_cap(monkeypatch):
    """Verify that /health and /api/health are exempt from concurrency caps even when cap=0."""
    monkeypatch.setattr(settings, "MAX_CONCURRENT_UPLOADS", 0)

    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "ok"

    res_api_health = client.get("/api/health")
    assert res_api_health.status_code == 200
    assert res_api_health.json()["status"] == "healthy"


def test_rate_limiter_placeholder_middleware_inert():
    """Verify RateLimiterPlaceholderMiddleware remains inert and passes requests through."""
    assert settings.ENABLE_RATE_LIMITING is False
    # Send multiple rapid health checks through the middleware stack
    for _ in range(15):
        res = client.get("/health")
        assert res.status_code == 200
