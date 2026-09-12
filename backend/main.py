"""FastAPI Main Application for Foresight backend."""

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from config.settings import settings
from src.memory.lifecycle import ephemeral_processing


class RateLimiterPlaceholderMiddleware(BaseHTTPMiddleware):
    """Placeholder rate-limiting middleware.

    Checks `settings.ENABLE_RATE_LIMITING` and no-ops if False,
    ensuring it is inert during Phases 2-4 and will not throttle local dev/testing.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.ENABLE_RATE_LIMITING:
            # Inert placeholder — no-op
            return await call_next(request)

        # Rate limiting logic scaffold (deferred to Phase 5)
        return await call_next(request)


app = FastAPI(
    title="Foresight Engine API",
    description="Backend API for Foresight data ingestion, statistical modeling, and document intelligence.",
    version="0.2.0",
)

# 1. Rate Limiting Middleware (inert placeholder)
app.add_middleware(RateLimiterPlaceholderMiddleware)

# 2. CORS Middleware allowing Next.js frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "rate_limiting_enabled": settings.ENABLE_RATE_LIMITING,
        "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
    }


@app.post("/upload")
async def upload():
    """Empty POST /upload route stub to be filled in a later prompt."""
    with ephemeral_processing():
        return {"message": "Upload stub"}
