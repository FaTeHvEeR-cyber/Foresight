"""Application configuration and settings for Foresight backend."""

from typing import List, Set
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_NAME: str = "Foresight Backend"
    APP_VERSION: str = "0.2.0"
    DEBUG: bool = False

    # Security & Guardrails (Phase 2)
    # 25MB hard file size limit
    MAX_FILE_SIZE_BYTES: int = 25 * 1024 * 1024  # 26,214,400 bytes

    # Ephemeral in-memory session TTL (1 hour)
    SESSION_TTL_SECONDS: int = 3600

    # Rate limiting placeholder (Deferred to Phase 5, inert by default)
    ENABLE_RATE_LIMITING: bool = False
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60

    # CORS settings
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    # File format categories
    TABULAR_EXTENSIONS: Set[str] = {"csv", "tsv", "xlsx", "xls", "parquet"}
    DOCUMENT_EXTENSIONS: Set[str] = {"pdf", "docx", "txt", "md"}

    @property
    def ALLOWED_EXTENSIONS(self) -> Set[str]:
        return self.TABULAR_EXTENSIONS | self.DOCUMENT_EXTENSIONS


settings = Settings()
