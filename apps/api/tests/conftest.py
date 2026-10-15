from collections.abc import Iterator

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import text

from sendox_api.config import Settings
from sendox_api.db import get_sessionmaker
from sendox_api.main import create_app

# Every account a test creates uses this domain, which gives the cleanup below a
# precise handle and can never match a real user.
TEST_EMAIL_DOMAIN = "example.com"


@pytest.fixture
def settings() -> Settings:
    return Settings(env="test", log_level="WARNING")


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


@pytest.fixture(scope="session", autouse=True)
def _purge_test_data() -> Iterator[None]:
    """Remove accounts and workspaces the suite created, once it has finished.

    The tests run against the development database, so without this every run
    leaves users and tenants behind and the dataset grows forever.

    The hard requirement is the other direction, and it was violated once: this
    must never delete anything the suite did not create. The previous version
    deleted every tenant that had no memberships, which sounds like "orphans the
    suite left behind" and is not. Deleting the suite's `@example.com` users
    cascades their memberships away, so a *developer's* workspace whose only
    member happened to be such an account becomes memberless in the same
    transaction and is then deleted too, taking its connected Shopify store with
    it. That is what happened: a real store connection, gone, because the test
    suite ran.

    So the set of tenants that existed before the suite started is recorded up
    front, and nothing in that set is ever touched.
    """
    settings = Settings(env="test", log_level="WARNING")

    pre_existing: set[str] = set()
    try:
        with get_sessionmaker(settings)() as session:
            pre_existing = {str(row[0]) for row in session.execute(text("SELECT id FROM tenants"))}
    except sqlalchemy.exc.SQLAlchemyError:
        # No database here; the tests that needed one will skip.
        yield
        return

    yield

    try:
        with get_sessionmaker(settings)() as session:
            # Deleting a user cascades to memberships, email tokens and audit
            # entries; tenants are not owned by a user, so orphans go after.
            session.execute(
                text("DELETE FROM users WHERE email LIKE :pattern"),
                {"pattern": f"%@{TEST_EMAIL_DOMAIN}"},
            )
            if pre_existing:
                session.execute(
                    text(
                        "DELETE FROM tenants t WHERE NOT EXISTS "
                        "(SELECT 1 FROM memberships m WHERE m.tenant_id = t.id) "
                        "AND t.id <> ALL(:keep)"
                    ),
                    {"keep": list(pre_existing)},
                )
            else:
                session.execute(
                    text(
                        "DELETE FROM tenants t WHERE NOT EXISTS "
                        "(SELECT 1 FROM memberships m WHERE m.tenant_id = t.id)"
                    )
                )
            session.commit()
    except sqlalchemy.exc.SQLAlchemyError:
        return
