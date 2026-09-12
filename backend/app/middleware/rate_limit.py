"""Rate limiting middleware placeholder (scaffolded for Phase 5, inert by default)."""

import time
from collections import defaultdict, deque
from typing import DefaultDict, Deque
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from fastapi import status

from app.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Lightweight in-memory sliding window rate limiter placeholder.
    Inert during Phases 2-4 (ENABLE_RATE_LIMITING = False) to prevent throttling local dev/testing.
    Can be toggled via ENABLE_RATE_LIMITING=True in settings/env.
    """

    def __init__(self, app):
        super().__init__(app)
        # Store timestamps of requests per IP: IP -> deque([timestamps])
        self._request_history: DefaultDict[str, Deque[float]] = defaultdict(deque)

    def reset(self) -> None:
        """Reset internal rate tracking history (useful for testing)."""
        self._request_history.clear()

    async def dispatch(self, request: Request, call_next) -> Response:
        # If rate limiting is disabled (default in Phase 2), pass request through immediately
        if not settings.ENABLE_RATE_LIMITING:
            return await call_next(request)

        # Rate limiting logic active only when ENABLE_RATE_LIMITING=True
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_seconds = 60.0
        max_requests = settings.RATE_LIMIT_REQUESTS_PER_MINUTE

        history = self._request_history[client_ip]

        # Purge timestamps outside the sliding window
        while history and history[0] < (now - window_seconds):
            history.popleft()

        if len(history) >= max_requests:
            retry_after = int(window_seconds - (now - history[0])) + 1
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Rate limit exceeded. Please wait before submitting more requests."
                },
                headers={"Retry-After": str(max(1, retry_after))},
            )

        history.append(now)
        return await call_next(request)
