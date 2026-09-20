"""Application configuration compatibility layer for legacy app module."""

from config.settings import Settings as CanonicalSettings, get_settings


class Settings(CanonicalSettings):
    """Subclass of canonical Settings preserving legacy 25MB default for app/ tests."""

    MAX_FILE_SIZE_MB: int = 25


settings = Settings()
