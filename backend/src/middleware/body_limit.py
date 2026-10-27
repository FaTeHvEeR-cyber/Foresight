"""ASGI middleware for early ingress body limits on file upload routes (F-09).

Rejects oversized request bodies before buffering or reading them into memory:
- Fast path: If Content-Length header is present and > MAX_INGRESS_BODY_BYTES,
  returns HTTP 413 immediately without reading any body bytes.
- Streaming/chunked: Wraps receive() and aborts with HTTP 413 once accumulated
  received bytes exceed MAX_INGRESS_BODY_BYTES.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Optional, Set

from fastapi import HTTPException
from config.settings import settings


class BodyLimitMiddleware:
    """Pure ASGI middleware enforcing ingress body limits on file upload routes."""

    DEFAULT_PROTECTED_PATHS: Set[str] = {
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
        max_body_bytes: Optional[int] = None,
        protected_paths: Optional[Set[str]] = None,
    ):
        self.app = app
        self.max_body_bytes = (
            max_body_bytes
            if max_body_bytes is not None
            else settings.MAX_INGRESS_BODY_BYTES
        )
        self.protected_paths = (
            protected_paths
            if protected_paths is not None
            else self.DEFAULT_PROTECTED_PATHS
        )

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Any],
        send: Callable[..., Any],
    ) -> None:
        if scope.get("type") == "http" and scope.get("method") == "POST":
            raw_path = scope.get("path", "")
            path = raw_path.rstrip("/")
            if path in self.protected_paths:
                headers = dict(scope.get("headers", []))
                cl_header = headers.get(b"content-length")
                if cl_header:
                    try:
                        content_length = int(cl_header.decode("ascii"))
                        if content_length > self.max_body_bytes:
                            # Fast path: reject immediately before reading any body
                            await self._send_413_response(send, content_length)
                            return
                    except ValueError:
                        pass

                # Streaming / chunked / absent Content-Length path
                received_bytes = 0
                response_started = False

                async def wrapped_send(message: dict[str, Any]) -> None:
                    nonlocal response_started
                    if message["type"] == "http.response.start":
                        response_started = True
                    await send(message)

                async def wrapped_receive() -> dict[str, Any]:
                    nonlocal received_bytes
                    message = await receive()
                    if message["type"] == "http.request":
                        chunk = message.get("body", b"")
                        received_bytes += len(chunk)
                        if received_bytes > self.max_body_bytes:
                            raise HTTPException(
                                status_code=413,
                                detail=settings.error_upload_size_exceeded(received_bytes),
                            )
                    return message

                try:
                    await self.app(scope, wrapped_receive, wrapped_send)
                    return
                except HTTPException as exc:
                    if not response_started and exc.status_code == 413:
                        await self._send_413_response(
                            send,
                            received_bytes or self.max_body_bytes,
                            detail=exc.detail,
                        )
                        return
                    raise

        await self.app(scope, receive, send)

    async def _send_413_response(
        self,
        send: Callable[..., Any],
        uploaded_bytes: int,
        detail: Optional[str] = None,
    ) -> None:
        error_detail = detail or settings.error_upload_size_exceeded(uploaded_bytes)
        body = json.dumps({"detail": error_detail}).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })
