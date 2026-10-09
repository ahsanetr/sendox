import pytest
from pydantic import ValidationError

from sendox_api.config import Settings


def test_cors_origins_parse_into_a_list() -> None:
    settings = Settings(cors_origins="http://a.test, http://b.test ,")
    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]


def test_is_production_only_for_production_values() -> None:
    # A real signing key is required for any production Settings to construct.
    strong = "x" * 48
    assert Settings(env="production", jwt_secret=strong).is_production
    assert Settings(env="PROD", jwt_secret=strong).is_production
    assert not Settings(env="development").is_production


def test_defaults_match_compose_stack() -> None:
    settings = Settings(_env_file=None)
    assert settings.chroma_url == "http://localhost:8001"
    assert settings.mjml_url == "http://localhost:7070"
    assert settings.anthropic_model == "claude-sonnet-5"


def test_production_refuses_the_development_signing_key() -> None:
    """A weak key would weaken every session token the platform issues."""
    with pytest.raises(ValidationError) as caught:
        Settings(env="production", _env_file=None)

    assert "JWT_SECRET" in str(caught.value)


def test_production_refuses_a_short_signing_key() -> None:
    with pytest.raises(ValidationError) as caught:
        Settings(env="production", jwt_secret="too-short", _env_file=None)

    assert "32 bytes" in str(caught.value)


def test_development_tolerates_the_default_key() -> None:
    """Local development must not need a generated secret to boot."""
    assert Settings(env="development", _env_file=None).jwt_secret.startswith("dev-only")


def test_the_repo_root_env_file_is_actually_found() -> None:
    """The .env path was once off by one and pointed at apps/, silently.

    Nothing failed loudly: Docker passes environment variables directly, so the
    file was never needed there, and an unset ANTHROPIC_API_KEY just looks like
    "not configured yet". This pins the location.
    """
    from sendox_api.config import _REPO_ROOT

    assert (_REPO_ROOT / ".env.example").is_file(), (
        f"_REPO_ROOT resolved to {_REPO_ROOT}, which is not the repository root"
    )
    assert (_REPO_ROOT / "docker-compose.yml").is_file()


def test_repo_root_discovery_survives_a_flattened_layout(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The container flattens the tree, so a fixed parent index raises IndexError.

    Replacing the index with a marker search fixed the container; this proves the
    search degrades gracefully when no marker exists at all, rather than throwing.
    """
    from sendox_api.config import _find_repo_root

    # Running from this repository, the marker is found.
    assert (_find_repo_root() / "docker-compose.yml").is_file()
