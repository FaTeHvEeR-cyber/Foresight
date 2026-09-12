"""Request and file size guardrail middleware."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from fastapi import status

from app.config import settings


class FileSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Guards the server by checking Content-Length early before reading bodies.
    Hard limits uploads to 25MB.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                length = int(content_length)
                if length > settings.MAX_FILE_SIZE_BYTES:
                    max_mb = settings.MAX_FILE_SIZE_BYTES / (1024 * 1024)
                    uploaded_mb = length / (1024 * 1024)
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={
                            "detail": (
                                f"File exceeds the 25MB limit "
                                f"({uploaded_mb:.2f} MB, max is {max_mb:.0f} MB)."
                            )
                        },
                    )
            except ValueError:
                pass

        return await call_next(request)
