"""FastAPI main application entrypoint for Foresight backend."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.size_guard import FileSizeLimitMiddleware
from app.routers import health, ingestion


def create_app() -> FastAPI:
    app = FastAPI(
        title="Foresight Backend API",
        version=settings.APP_VERSION,
        description="Stateless in-memory analytics engine supporting time-series forecasting, segmentation, and document summarization.",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 1. CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Security Gatekeeper: 25MB File Size Guardrail
    app.add_middleware(FileSizeLimitMiddleware)

    # 3. Rate Limiting Middleware placeholder (inert during Phases 2-4)
    app.add_middleware(RateLimitMiddleware)

    # 4. Include Routers
    app.include_router(health.router)
    app.include_router(ingestion.router)

    # Root welcome / ping
    @app.get("/", tags=["root"])
    async def root():
        return {
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "online",
            "docs": "/docs",
        }

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
