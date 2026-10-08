"""Dev capability-check endpoints.

The MJML tests need the sidecar running, so they are marked `integration` and
skipped when it is not reachable — `pytest -q` stays useful with nothing booted.
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from sendox_api.config import Settings
from sendox_api.main import create_app


def _mjml_up(settings: Settings) -> bool:
    try:
        return httpx.get(f"{settings.mjml_url}/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


def test_dev_routes_are_absent_in_production() -> None:
    # FastAPI 0.142 wraps included routers instead of flattening them into
    # `app.routes`, so the OpenAPI schema is the reliable view of mounted paths.
    production = create_app(Settings(env="production", log_level="WARNING"))
    paths = production.openapi()["paths"]

    assert not any(path.startswith("/dev") for path in paths)
    assert "/status/modules" in paths
    assert "/health/ready" in paths


def test_dev_routes_are_present_in_development(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/dev/mjml/render" in paths
    assert "/dev/tasks/ping" in paths


@pytest.mark.integration
def test_mjml_render_round_trip(client: TestClient, settings: Settings) -> None:
    if not _mjml_up(settings):
        pytest.skip("MJML sidecar not running")

    body = client.post("/dev/mjml/render", json={}).json()

    assert body["ok"] is True
    assert body["errors"] == []
    assert body["responsive"] is True
    assert body["html_bytes"] > 1000


@pytest.mark.integration
def test_mjml_render_reports_invalid_markup(client: TestClient, settings: Settings) -> None:
    if not _mjml_up(settings):
        pytest.skip("MJML sidecar not running")

    body = client.post(
        "/dev/mjml/render",
        json={"mjml": "<mjml><mj-body><mj-text>loose</mj-text></mj-body></mjml>"},
    ).json()

    assert body["ok"] is False
    assert body["errors"][0]["tagName"] == "mj-text"
