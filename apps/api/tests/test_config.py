from sendox_api.config import Settings


def test_cors_origins_parse_into_a_list() -> None:
    settings = Settings(cors_origins="http://a.test, http://b.test ,")
    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]


def test_is_production_only_for_production_values() -> None:
    assert Settings(env="production").is_production
    assert Settings(env="PROD").is_production
    assert not Settings(env="development").is_production


def test_defaults_match_compose_stack() -> None:
    settings = Settings(_env_file=None)
    assert settings.chroma_url == "http://localhost:8001"
    assert settings.mjml_url == "http://localhost:7070"
    assert settings.anthropic_model == "claude-sonnet-5"
