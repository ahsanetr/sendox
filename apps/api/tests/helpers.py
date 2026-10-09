"""Shared helpers for the M1 integration tests."""

import uuid
from dataclasses import dataclass

from fastapi.testclient import TestClient


def unique_email(prefix: str = "user") -> str:
    # A real TLD: EmailStr rejects reserved ones such as .test and .local, which
    # is correct for a platform whose whole job is delivering mail.
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"


STRONG_PASSWORD = "Northwind2026"


@dataclass
class Account:
    email: str
    password: str
    token: str
    user_id: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


def register_and_verify(
    client: TestClient,
    *,
    prefix: str = "user",
    workspace_name: str | None = None,
    password: str = STRONG_PASSWORD,
) -> Account:
    """Create a confirmed, signed-in account.

    Uses the development-only token in the register response, so the tests need no
    mail server at all.
    """
    email = unique_email(prefix)
    created = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": prefix.title(),
            "workspace_name": workspace_name,
        },
    )
    assert created.status_code == 201, created.text
    verification_token = created.json()["dev_verification_token"]
    assert verification_token, "development builds must return the token"

    verified = client.post("/auth/verify-email", json={"token": verification_token})
    assert verified.status_code == 200, verified.text
    body = verified.json()

    # The client keeps the session cookie too; drop it so each request's identity
    # comes from the explicit bearer header and tests cannot pass by accident.
    client.cookies.clear()

    return Account(
        email=email,
        password=password,
        token=body["access_token"],
        user_id=body["user"]["id"],
    )


def first_workspace(client: TestClient, account: Account) -> dict[str, str]:
    body = client.get("/auth/me", headers=account.auth).json()
    assert body["workspaces"], "account has no workspace"
    workspace: dict[str, str] = body["workspaces"][0]
    return workspace


def delete_account(client: TestClient, account: Account) -> None:
    client.delete("/auth/me", headers=account.auth)
    client.cookies.clear()
