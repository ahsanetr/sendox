"""Workspaces, roles, invitations and isolation (scope M1 FE-4/5/7).

The questions these answer are the ones a multi-tenant SaaS gets wrong quietly:
can a non-member reach a workspace, can a viewer act like an admin, can a
workspace lose its last owner, and does deleting an account take someone else's
data with it.
"""

import pytest
import sqlalchemy
from fastapi.testclient import TestClient

from sendox_api.config import Settings
from sendox_api.db import get_sessionmaker
from tests.helpers import delete_account, first_workspace, register_and_verify

pytestmark = pytest.mark.integration


def _database_up(settings: Settings) -> bool:
    try:
        with get_sessionmaker(settings)() as session:
            session.execute(sqlalchemy.text("SELECT 1"))
        return True
    except sqlalchemy.exc.SQLAlchemyError:
        return False


@pytest.fixture(autouse=True)
def _needs_database(settings: Settings) -> None:
    if not _database_up(settings):
        pytest.skip("Postgres not running — start it with `make up` or `make up-native`")


def _invite(client: TestClient, owner, workspace_id: str, email: str, role: str) -> str:
    """Invite someone and return the token the email would have carried."""
    response = client.post(
        f"/workspaces/{workspace_id}/invitations",
        json={"email": email, "role": role},
        headers=owner.auth,
    )
    assert response.status_code == 201, response.text
    token: str = response.json()["dev_invitation_token"]
    return token


def test_the_creator_of_a_workspace_is_its_owner(client: TestClient) -> None:
    account = register_and_verify(client, prefix="owner", workspace_name="Northwind Supply")

    workspace = first_workspace(client, account)

    assert workspace["name"] == "Northwind Supply"
    # Only the prefix is asserted: a workspace of this name may already exist in
    # the shared development database, in which case the slug gains a suffix.
    # Uniqueness itself is covered by test_slugs_stay_unique_across_workspaces.
    assert workspace["slug"].startswith("northwind-supply")
    assert workspace["role"] == "owner"
    delete_account(client, account)


def test_slugs_stay_unique_across_workspaces_of_the_same_name(client: TestClient) -> None:
    first = register_and_verify(client, prefix="a", workspace_name="Duplicate Name")
    second = register_and_verify(client, prefix="b", workspace_name="Duplicate Name")

    slugs = {
        first_workspace(client, first)["slug"],
        first_workspace(client, second)["slug"],
    }

    assert len(slugs) == 2
    delete_account(client, first)
    delete_account(client, second)


def test_a_non_member_cannot_see_that_a_workspace_exists(client: TestClient) -> None:
    """404 rather than 403: existence itself should not leak."""
    owner = register_and_verify(client, prefix="owner", workspace_name="Private Brand")
    outsider = register_and_verify(client, prefix="outsider")
    workspace_id = first_workspace(client, owner)["id"]

    response = client.get(f"/workspaces/{workspace_id}", headers=outsider.auth)

    assert response.status_code == 404
    delete_account(client, owner)
    delete_account(client, outsider)


def test_each_account_lists_only_its_own_workspaces(client: TestClient) -> None:
    first = register_and_verify(client, prefix="first", workspace_name="First Brand")
    second = register_and_verify(client, prefix="second", workspace_name="Second Brand")

    names = {w["name"] for w in client.get("/auth/me", headers=first.auth).json()["workspaces"]}

    assert names == {"First Brand"}
    delete_account(client, first)
    delete_account(client, second)


def test_an_invitation_grants_access_only_after_it_is_accepted(client: TestClient) -> None:
    owner = register_and_verify(client, prefix="owner", workspace_name="Northwind")
    invitee = register_and_verify(client, prefix="invitee")
    workspace_id = first_workspace(client, owner)["id"]
    token = _invite(client, owner, workspace_id, invitee.email, "viewer")

    before = client.get(f"/workspaces/{workspace_id}", headers=invitee.auth)
    accepted = client.post("/invitations/accept", json={"token": token}, headers=invitee.auth)
    after = client.get(f"/workspaces/{workspace_id}", headers=invitee.auth)

    assert before.status_code == 404
    assert accepted.status_code == 200
    assert after.status_code == 200
    assert after.json()["role"] == "viewer"
    delete_account(client, invitee)
    delete_account(client, owner)


def test_an_invitation_cannot_be_redeemed_by_someone_else(client: TestClient) -> None:
    """A leaked link must not work for whoever finds it."""
    owner = register_and_verify(client, prefix="owner", workspace_name="Northwind")
    invitee = register_and_verify(client, prefix="invitee")
    bystander = register_and_verify(client, prefix="bystander")
    workspace_id = first_workspace(client, owner)["id"]
    token = _invite(client, owner, workspace_id, invitee.email, "editor")

    response = client.post("/invitations/accept", json={"token": token}, headers=bystander.auth)

    assert response.status_code == 403
    assert invitee.email in response.json()["detail"]
    for account in (bystander, invitee, owner):
        delete_account(client, account)


def test_an_invitation_preview_needs_no_account(client: TestClient) -> None:
    owner = register_and_verify(client, prefix="owner", workspace_name="Northwind")
    workspace_id = first_workspace(client, owner)["id"]
    token = _invite(client, owner, workspace_id, "newcomer@example.com", "editor")

    response = client.post("/invitations/preview", json={"token": token})

    assert response.status_code == 200
    assert response.json()["workspace"] == "Northwind"
    assert response.json()["role"] == "editor"
    delete_account(client, owner)


def test_an_invitation_token_works_only_once(client: TestClient) -> None:
    owner = register_and_verify(client, prefix="owner", workspace_name="Northwind")
    invitee = register_and_verify(client, prefix="invitee")
    workspace_id = first_workspace(client, owner)["id"]
    token = _invite(client, owner, workspace_id, invitee.email, "viewer")
    client.post("/invitations/accept", json={"token": token}, headers=invitee.auth)

    replayed = client.post("/invitations/accept", json={"token": token}, headers=invitee.auth)

    assert replayed.status_code == 400
    delete_account(client, invitee)
    delete_account(client, owner)


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("patch", "", {"name": "Renamed"}),
        ("post", "/invitations", {"email": "someone@example.com", "role": "viewer"}),
        ("get", "/audit", None),
    ],
)
def test_a_viewer_cannot_perform_privileged_actions(
    client: TestClient, method: str, path: str, payload: dict[str, str] | None
) -> None:
    owner = register_and_verify(client, prefix="owner", workspace_name="Northwind")
    viewer = register_and_verify(client, prefix="viewer")
    workspace_id = first_workspace(client, owner)["id"]
    token = _invite(client, owner, workspace_id, viewer.email, "viewer")
    client.post("/invitations/accept", json={"token": token}, headers=viewer.auth)

    request = getattr(client, method)
    url = f"/workspaces/{workspace_id}{path}"
    response = (
        request(url, json=payload, headers=viewer.auth)
        if payload
        else request(url, headers=viewer.auth)
    )

    assert response.status_code == 403
    assert "viewer" in response.json()["detail"]
    delete_account(client, viewer)
    delete_account(client, owner)


def test_an_admin_cannot_promote_anyone_to_owner(client: TestClient) -> None:
    """Ownership is the one role an admin must not be able to hand out."""
    owner = register_and_verify(client, prefix="owner", workspace_name="Northwind")
    admin = register_and_verify(client, prefix="admin")
    workspace_id = first_workspace(client, owner)["id"]
    token = _invite(client, owner, workspace_id, admin.email, "admin")
    client.post("/invitations/accept", json={"token": token}, headers=admin.auth)

    response = client.patch(
        f"/workspaces/{workspace_id}/members/{admin.user_id}",
        json={"role": "owner"},
        headers=admin.auth,
    )

    assert response.status_code == 403
    delete_account(client, admin)
    delete_account(client, owner)


def test_a_workspace_cannot_lose_its_last_owner(client: TestClient) -> None:
    owner = register_and_verify(client, prefix="owner", workspace_name="Northwind")
    workspace_id = first_workspace(client, owner)["id"]

    demoted = client.patch(
        f"/workspaces/{workspace_id}/members/{owner.user_id}",
        json={"role": "admin"},
        headers=owner.auth,
    )
    removed = client.delete(
        f"/workspaces/{workspace_id}/members/{owner.user_id}", headers=owner.auth
    )

    assert demoted.status_code == 409
    assert removed.status_code == 409
    delete_account(client, owner)


def test_an_owner_can_update_settings_and_it_is_audited(client: TestClient) -> None:
    owner = register_and_verify(client, prefix="owner", workspace_name="Northwind")
    workspace_id = first_workspace(client, owner)["id"]

    updated = client.patch(
        f"/workspaces/{workspace_id}",
        json={"name": "Northwind Supply Co", "timezone": "Asia/Karachi"},
        headers=owner.auth,
    )
    entries = client.get(f"/workspaces/{workspace_id}/audit", headers=owner.auth).json()

    assert updated.json()["name"] == "Northwind Supply Co"
    assert updated.json()["timezone"] == "Asia/Karachi"
    actions = [entry["action"] for entry in entries]
    assert "workspace.created" in actions
    assert "workspace.updated" in actions
    delete_account(client, owner)


def test_the_audit_log_is_scoped_to_one_workspace(client: TestClient) -> None:
    """Two workspaces owned by the same person must not share history."""
    owner = register_and_verify(client, prefix="owner", workspace_name="First Brand")
    second = client.post("/workspaces", json={"name": "Second Brand"}, headers=owner.auth).json()
    first_id = first_workspace(client, owner)["id"]
    client.patch(f"/workspaces/{first_id}", json={"name": "First Renamed"}, headers=owner.auth)

    second_entries = client.get(f"/workspaces/{second['id']}/audit", headers=owner.auth).json()

    targets = {entry["target"] for entry in second_entries}
    assert "first-brand" not in targets
    assert all(entry["action"] != "workspace.updated" for entry in second_entries)
    delete_account(client, owner)


def test_deleting_an_account_keeps_workspaces_that_others_still_use(
    client: TestClient,
) -> None:
    owner = register_and_verify(client, prefix="owner", workspace_name="Shared Brand")
    member = register_and_verify(client, prefix="member", workspace_name="Solo Brand")
    workspace_id = first_workspace(client, owner)["id"]
    token = _invite(client, owner, workspace_id, member.email, "editor")
    client.post("/invitations/accept", json={"token": token}, headers=member.auth)

    removed = client.delete("/auth/me", headers=member.auth).json()
    client.cookies.clear()
    remaining = client.get(f"/workspaces/{workspace_id}/members", headers=owner.auth).json()

    # Their own solo workspace is purged; the shared one survives without them.
    assert removed["workspaces_deleted"] == 1
    assert removed["memberships_removed"] == 2
    assert [m["email"] for m in remaining] == [owner.email]
    delete_account(client, owner)
