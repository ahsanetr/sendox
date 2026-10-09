"""Registration, verification, sign-in and password handling (scope M1 FE-1/2/3).

Integration tests: they exercise the real database, because most of what matters
here — single-use tokens, uniqueness, cascading deletes — is enforced there.
"""

import pytest
import sqlalchemy
from fastapi.testclient import TestClient

from sendox_api.config import Settings
from sendox_api.db import get_sessionmaker
from sendox_api.main import create_app
from tests.helpers import STRONG_PASSWORD, delete_account, register_and_verify, unique_email

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


def test_registration_creates_an_unverified_account(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        json={"email": unique_email(), "password": STRONG_PASSWORD, "full_name": "Test Person"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email_verified"] is False
    assert body["dev_verification_token"]


def test_sign_in_is_refused_until_the_address_is_confirmed(client: TestClient) -> None:
    email = unique_email()
    client.post("/auth/register", json={"email": email, "password": STRONG_PASSWORD})

    response = client.post("/auth/login", json={"email": email, "password": STRONG_PASSWORD})

    # 403, not 401: the credentials were right, the account is simply not ready.
    assert response.status_code == 403
    assert "confirm" in response.json()["detail"].lower()


def test_confirming_the_address_also_signs_the_user_in(client: TestClient) -> None:
    email = unique_email()
    created = client.post("/auth/register", json={"email": email, "password": STRONG_PASSWORD})
    token = created.json()["dev_verification_token"]

    response = client.post("/auth/verify-email", json={"token": token})

    assert response.status_code == 200
    assert response.json()["user"]["email_verified"] is True
    assert response.json()["access_token"]


def test_a_verification_link_works_only_once(client: TestClient) -> None:
    created = client.post(
        "/auth/register", json={"email": unique_email(), "password": STRONG_PASSWORD}
    )
    token = created.json()["dev_verification_token"]
    client.post("/auth/verify-email", json={"token": token})

    replayed = client.post("/auth/verify-email", json={"token": token})

    assert replayed.status_code == 400


def test_the_session_cookie_is_not_readable_by_page_scripts(client: TestClient) -> None:
    created = client.post(
        "/auth/register", json={"email": unique_email(), "password": STRONG_PASSWORD}
    )
    response = client.post(
        "/auth/verify-email", json={"token": created.json()["dev_verification_token"]}
    )

    cookie_header = response.headers["set-cookie"].lower()
    assert "httponly" in cookie_header
    assert "samesite=lax" in cookie_header


@pytest.mark.parametrize(
    ("password", "expected"),
    [
        ("Short1", "at least"),
        ("alllowercase1", "upper and lower"),
        ("NoDigitsHere", "digit"),
    ],
)
def test_weak_passwords_are_refused_with_a_reason(
    client: TestClient, password: str, expected: str
) -> None:
    response = client.post("/auth/register", json={"email": unique_email(), "password": password})

    assert response.status_code == 422
    assert any(expected in problem for problem in _problems(response.json()["detail"]))


def _problems(detail: object) -> list[str]:
    """Pydantic and our own validation report errors differently; flatten both."""
    if isinstance(detail, list):
        return [item if isinstance(item, str) else str(item.get("msg", item)) for item in detail]
    return [str(detail)]


def test_an_address_cannot_be_registered_twice(client: TestClient) -> None:
    email = unique_email()
    client.post("/auth/register", json={"email": email, "password": STRONG_PASSWORD})

    response = client.post("/auth/register", json={"email": email, "password": STRONG_PASSWORD})

    assert response.status_code == 409


def test_the_wrong_password_is_refused(client: TestClient) -> None:
    account = register_and_verify(client)

    response = client.post("/auth/login", json={"email": account.email, "password": "Wrong2026xx"})

    assert response.status_code == 401
    delete_account(client, account)


def test_a_reset_request_reveals_nothing_about_unknown_addresses(client: TestClient) -> None:
    """Otherwise the endpoint becomes a way to discover who has an account."""
    known = register_and_verify(client)

    for_known = client.post(
        "/auth/forgot-password", json={"email": known.email, "password": "unused"}
    )
    for_unknown = client.post(
        "/auth/forgot-password", json={"email": unique_email(), "password": "unused"}
    )

    assert for_known.status_code == for_unknown.status_code == 200
    assert for_known.json()["status"] == for_unknown.json()["status"]
    assert for_unknown.json()["dev_reset_token"] is None
    delete_account(client, known)


def test_resetting_the_password_invalidates_the_old_one(client: TestClient) -> None:
    account = register_and_verify(client)
    requested = client.post(
        "/auth/forgot-password", json={"email": account.email, "password": "unused"}
    )

    reset = client.post(
        "/auth/reset-password",
        json={"token": requested.json()["dev_reset_token"], "password": "Replacement2026"},
    )
    client.cookies.clear()

    assert reset.status_code == 200
    assert (
        client.post(
            "/auth/login", json={"email": account.email, "password": account.password}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/auth/login", json={"email": account.email, "password": "Replacement2026"}
        ).status_code
        == 200
    )
    client.cookies.clear()


def test_changing_the_password_requires_the_current_one(client: TestClient) -> None:
    account = register_and_verify(client)

    refused = client.post(
        "/auth/change-password",
        json={"current_password": "Wrong2026xx", "new_password": "Replacement2026"},
        headers=account.auth,
    )
    accepted = client.post(
        "/auth/change-password",
        json={"current_password": account.password, "new_password": "Replacement2026"},
        headers=account.auth,
    )

    assert refused.status_code == 400
    assert accepted.status_code == 200
    delete_account(client, account)


def test_endpoints_require_a_session(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_a_deleted_account_cannot_be_used(client: TestClient) -> None:
    account = register_and_verify(client)

    removed = client.delete("/auth/me", headers=account.auth)

    assert removed.status_code == 200
    assert client.get("/auth/me", headers=account.auth).status_code == 401


def test_development_only_tokens_are_absent_in_production(settings: Settings) -> None:
    """The dev token shortcut must never reach a real deployment."""
    production = create_app(
        Settings(
            env="production",
            log_level="WARNING",
            jwt_secret="a" * 48,  # production refuses the dev defaults
            encryption_key="b" * 48,
        )
    )
    with TestClient(production) as production_client:
        response = production_client.post(
            "/auth/register", json={"email": unique_email(), "password": STRONG_PASSWORD}
        )

    assert response.status_code == 201
    assert response.json()["dev_verification_token"] is None
    assert response.json()["dev_hint"] is None
