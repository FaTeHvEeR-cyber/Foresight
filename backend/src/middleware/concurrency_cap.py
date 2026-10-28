"""ASGI middleware for per-process upload and analytics concurrency capping.

Enforces Decision D-S1 Option B per-process concurrency control on memory-heavy
upload and statistical modeling endpoints (/upload, /forecast, /hypotheses, /segmentation).
Non-blocking acquire: rejects excess requests with HTTP 503 and 'Retry-After: 5'
without reading the request body.
Releases slots on normal completion, exception, and client disconnection/cancellation.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Optional, Set

from config.settings import settings


class UploadConcurrencyMiddleware:
    """Pure ASGI middleware enforcing a non-blocking per-process concurrency cap."""

    DEFAULT_CAPPED_PATHS: Set[str] = {
        "/api/v1/upload",
        "/upload",
        "/api/v1/forecast",
        "/forecast",
        "/api/v1/hypotheses",
        "/hypotheses",
        "/api/v1/segmentation",
        "/segmentation",
    }

    def __init__(
        self,
        app: Any,
        max_concurrent: Optional[int] = None,
        capped_paths: Optional[Set[str]] = None,
    ):
        self.app = app
        self._max_concurrent = max_concurrent
        self._capped_paths = (
            capped_paths
            if capped_paths is not None
            else self.DEFAULT_CAPPED_PATHS
        )
        self._active_count = 0

    @property
    def active_count(self) -> int:
        """Return the current number of in-flight requests holding a slot."""
        return self._active_count

    def get_max_concurrent(self) -> int:
        """Return effective max concurrent uploads, resolving dynamic settings if unset."""
        if self._max_concurrent is not None:
            return self._max_concurrent
        return getattr(settings, "MAX_CONCURRENT_UPLOADS", 2)

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Any],
        send: Callable[..., Any],
    ) -> None:
        if scope.get("type") == "http" and scope.get("method") == "POST":
            raw_path = scope.get("path", "")
            path = raw_path.rstrip("/")
            if path in self._capped_paths:
                max_allowed = self.get_max_concurrent()
                if self._active_count >= max_allowed:
                    # Non-blocking rejection: return 503 immediately without reading request body
                    await self._send_503_response(send)
                    return

                # Acquire slot
                self._active_count += 1
                try:
                    await self.app(scope, receive, send)
                finally:
                    # Release slot on success, error, or client cancellation/disconnect
                    self._active_count = max(0, self._active_count - 1)
                return

        await self.app(scope, receive, send)

    async def _send_503_response(self, send: Callable[..., Any]) -> None:
        body = json.dumps({
            "detail": "Server is handling maximum concurrent upload/analytics requests. Please retry shortly."
        }).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 503,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"retry-after", b"5"),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })
