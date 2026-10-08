import pytest
from fastapi.testclient import TestClient

from sendox_api.config import Settings
from sendox_api.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(env="test", log_level="WARNING")


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))
