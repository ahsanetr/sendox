from fastapi.testclient import TestClient


def test_root_identifies_the_service(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "sendox-api"


def test_openapi_schema_builds(client: TestClient) -> None:
    """Catches route/response-model mistakes without needing live services."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/health/ready" in response.json()["paths"]
