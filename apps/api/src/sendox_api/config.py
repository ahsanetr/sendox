"""Application settings, loaded from the environment or the repo-root .env."""

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py -> sendox_api -> src -> apps/api -> apps -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]

# RFC 7518 section 3.2: an HS256 key must be at least as long as the hash output.
MIN_JWT_SECRET_BYTES = 32


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

    # Auth. The default is long enough to satisfy HS256's 32-byte minimum and
    # obviously unusable in production, where `_reject_weak_secrets` refuses it.
    jwt_secret: str = "dev-only-insecure-secret-change-me-before-deploying"
    session_cookie_name: str = "sendox_session"

    # Mail. Defaults point at Mailpit in docker-compose; phase 1.10 swaps the host
    # for Amazon SES, which also speaks SMTP, so nothing else changes here.
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = False
    mail_from: str = "Sendox <no-reply@sendox.local>"

    # AI (wired up in phase 0.5)
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    # Only needed for an API key that is not scoped to a workspace
    # (sk-ant-usr-...). Console-issued keys carry their own workspace.
    anthropic_workspace_id: str | None = None
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # Observability
    sentry_dsn: str | None = None

    @model_validator(mode="after")
    def _reject_weak_secrets(self) -> "Settings":
        """Refuse to start a production app with a weak or default signing key.

        HS256 needs at least 32 bytes of key material; anything shorter weakens
        every session token the platform issues. Failing at startup is far better
        than discovering it from a forged token later.
        """
        if not self.is_production:
            return self

        if self.jwt_secret.startswith("dev-only"):
            raise ValueError(
                "JWT_SECRET is still the development default. "
                "Generate one with: openssl rand -base64 48"
            )
        if len(self.jwt_secret.encode()) < MIN_JWT_SECRET_BYTES:
            raise ValueError(
                f"JWT_SECRET must be at least {MIN_JWT_SECRET_BYTES} bytes for HS256; "
                f"got {len(self.jwt_secret.encode())}. "
                "Generate one with: openssl rand -base64 48"
            )
        return self

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
