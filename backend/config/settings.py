"""Application configuration and settings for Foresight backend."""

from typing import Any, List, Set
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App Metadata
    APP_NAME: str = "Foresight Backend"
    APP_VERSION: str = "0.2.0"
    DEBUG: bool = False

    # Ephemeral in-memory session TTL (1 hour)
    SESSION_TTL_SECONDS: int = 3600

    # API Keys & Models
    GOOGLE_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gemini-3.8-flash"

    # Guardrails
    MAX_FILE_SIZE_MB: int = 50
    UPLOAD_MAX_SIZE_BYTES: int = 50 * 1024 * 1024

    # File format categories
    TABULAR_EXTENSIONS: Set[str] = {"csv", "tsv", "xlsx", "xls", "parquet"}
    DOCUMENT_EXTENSIONS: Set[str] = {"pdf", "docx", "txt", "md"}

    # Allowed Extensions Whitelist
    ALLOWED_EXTENSIONS: Set[str] = {
        "csv",
        "tsv",
        "xlsx",
        "xls",
        "parquet",
        "pdf",
        "docx",
        "txt",
        "md",
    }

    # Allowed MIME Types Whitelist
    ALLOWED_MIME_TYPES: List[str] = [
        "text/csv",
        "text/plain",
        "text/tab-separated-values",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.apache.parquet",
        "application/x-parquet",
        "application/octet-stream",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/markdown",
    ]

    # Rate Limiting (Phase 2 scaffold, deferred to Phase 5)
    ENABLE_RATE_LIMITING: bool = False
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 30

    # Frontend Origin / CORS
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    # Phase 3A Analytics & Chart Picker
    LATENCY_BUDGET_MS: int = 200
    latency_budget_ms: int = 200
    google_api_key: str = ""
    llm_model: str = "gemini-3.8-flash"
    llm_timeout_s: float = 2.5
    LLM_TIMEOUT_S: float = 2.5
    chart_picker_enabled: bool = True
    CHART_PICKER_ENABLED: bool = True
    max_upload_bytes: int = 50 * 1024 * 1024

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    # Backwards compatibility alias
    @property
    def MAX_FILE_SIZE_BYTES(self) -> int:
        return self.max_file_size_bytes

    @property
    def active_api_key(self) -> str:
        return self.google_api_key or self.GOOGLE_API_KEY or self.LLM_API_KEY or self.GEMINI_API_KEY

    def model_post_init(self, __context: Any) -> None:
        key = self.google_api_key or self.GOOGLE_API_KEY or self.LLM_API_KEY or self.GEMINI_API_KEY
        object.__setattr__(self, "google_api_key", key)
        object.__setattr__(self, "GOOGLE_API_KEY", key)
        if self.max_upload_bytes != 50 * 1024 * 1024:
            object.__setattr__(self, "UPLOAD_MAX_SIZE_BYTES", self.max_upload_bytes)
            object.__setattr__(self, "MAX_FILE_SIZE_MB", self.max_upload_bytes // (1024 * 1024))
        elif self.UPLOAD_MAX_SIZE_BYTES != 50 * 1024 * 1024:
            object.__setattr__(self, "max_upload_bytes", self.UPLOAD_MAX_SIZE_BYTES)

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


def get_settings() -> Settings:
    """Return application settings singleton or instance for dependency injection."""
    return settings
