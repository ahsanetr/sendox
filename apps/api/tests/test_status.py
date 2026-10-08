from fastapi.testclient import TestClient


def test_module_manifest_covers_all_25_scope_modules(client: TestClient) -> None:
    body = client.get("/status/modules").json()

    assert len(body["modules"]) == 25
    assert [m["id"] for m in body["modules"]] == [f"M{n}" for n in range(1, 26)]


def test_every_item_has_a_known_status(client: TestClient) -> None:
    body = client.get("/status/modules").json()
    allowed = {"done", "in_progress", "partial", "planned"}

    for item in [*body["foundation"], *body["modules"]]:
        assert item["status"] in allowed, item
        assert item["release"] in {r["id"] for r in body["releases"]}, item


def test_totals_add_up(client: TestClient) -> None:
    body = client.get("/status/modules").json()
    totals = body["totals"]
    counted = totals.pop("items")

    assert counted == len(body["foundation"]) + len(body["modules"])
    assert sum(totals.values()) == counted
