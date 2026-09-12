"""Health check and service status endpoints."""

from fastapi import APIRouter
from app.config import settings
from app.models.schemas import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Service health and capability reporting."""
    return HealthResponse(
        status="healthy",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        max_file_size_bytes=settings.MAX_FILE_SIZE_BYTES,
        rate_limiting_enabled=settings.ENABLE_RATE_LIMITING,
        supported_formats=sorted(list(settings.ALLOWED_EXTENSIONS)),
    )
