"""Health endpoint contract.

These run without live services on purpose: the readiness endpoint must report a
dead dependency rather than raising, and that is exactly what CI needs to verify.
"""

from fastapi.testclient import TestClient


def test_liveness_never_depends_on_backing_services(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_reports_every_backing_service(client: TestClient) -> None:
    response = client.get("/health/ready")
    body = response.json()

    assert response.status_code in (200, 503)
    assert set(body["checks"]) == {"postgres", "redis", "chromadb", "mjml"}
    assert body["status"] in ("ok", "degraded")


def test_readiness_degrades_instead_of_raising(client: TestClient) -> None:
    """Point every probe at a dead port; the endpoint must still answer."""
    from sendox_api.config import Settings
    from sendox_api.main import create_app

    unreachable = Settings(
        env="test",
        log_level="WARNING",
        database_url="postgresql+psycopg://nobody:nobody@127.0.0.1:1/none",
        redis_url="redis://127.0.0.1:1/0",
        chroma_url="http://127.0.0.1:1",
        mjml_url="http://127.0.0.1:1",
    )
    with TestClient(create_app(unreachable)) as dead_client:
        response = dead_client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert all(check["status"] == "error" for check in body["checks"].values())
    assert all("detail" in check for check in body["checks"].values())
