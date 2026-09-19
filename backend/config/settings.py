"""Application configuration and settings for Foresight backend."""

from typing import List, Set
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # API Keys & Models
    GOOGLE_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    LLM_MODEL: str = "gemini-3.8-flash"

    # Guardrails
    MAX_FILE_SIZE_MB: int = 50
    UPLOAD_MAX_SIZE_BYTES: int = 50 * 1024 * 1024

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
    ]

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    # Backwards compatibility alias
    @property
    def MAX_FILE_SIZE_BYTES(self) -> int:
        return self.max_file_size_bytes

    @property
    def active_api_key(self) -> str:
        return self.GOOGLE_API_KEY or self.GEMINI_API_KEY

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
