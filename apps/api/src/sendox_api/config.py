"""Application settings, loaded from the environment or the repo-root .env."""

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_repo_root() -> Path:
    """Locate the repository root by searching upward for a marker file.

    Counting `.parents[N]` is fragile, because the layout differs by environment:
    in the repository this file sits at `apps/api/src/sendox_api/config.py`, but
    the container image flattens it to `/app/src/sendox_api/config.py`. An index
    that is correct for one raises IndexError on the other — which is exactly how
    the container's migrations broke once the index was "fixed" for the repo.

    `docker-compose.yml` is the marker because it is committed, so a fresh clone
    has it, unlike `.env`.
    """
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "docker-compose.yml").is_file():
            return candidate
    # Container image: the repository is not present and configuration arrives
    # through the environment, so point somewhere harmless that has no .env.
    return here.parent


_REPO_ROOT = _find_repo_root()

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

    # Master secret for credential encryption. Per-tenant keys are derived from
    # it, so this is the only value to rotate — but rotating it makes every
    # stored Shopify token unreadable, requiring a reconnect.
    encryption_key: str = "dev-only-insecure-encryption-key-change-me-too"
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

        if self.encryption_key.startswith("dev-only"):
            raise ValueError(
                "ENCRYPTION_KEY is still the development default. "
                "Generate one with: openssl rand -base64 48"
            )
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
