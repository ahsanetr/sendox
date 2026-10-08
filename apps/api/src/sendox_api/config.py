"""Application settings, loaded from the environment or the repo-root .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# src/sendox_api/config.py -> apps/api -> apps -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Every tunable the API reads. Defaults match docker-compose.yml."""

    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: str = "development"
    log_level: str = "INFO"

    # Backing services
    database_url: str = "postgresql+psycopg://sendox:sendox@localhost:5432/sendox"
    redis_url: str = "redis://localhost:6379/0"
    chroma_url: str = "http://localhost:8001"
    mjml_url: str = "http://localhost:7070"

    # The non-superuser role every application session switches into, so that
    # row-level security actually applies. Created by the initial migration.
    db_app_role: str = "sendox_app"

    # HTTP
    cors_origins: str = "http://localhost:3000"
    web_base_url: str = "http://localhost:3000"

    # Auth (wired up in phase 0.3)
    jwt_secret: str = "dev-only-change-me"

    # AI (wired up in phase 0.5)
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # Observability
    sentry_dsn: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.env.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    """Cached so settings are parsed once per process."""
    return Settings()
