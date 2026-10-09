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
    leaves users and tenants behind and the dataset grows forever. Tests delete
    their own accounts where it is part of what they assert; this is the net that
    catches the ones that fail early or create extra accounts on the way.
    """
    yield

    settings = Settings(env="test", log_level="WARNING")
    try:
        with get_sessionmaker(settings)() as session:
            # Deleting a user cascades to memberships, email tokens and audit
            # entries; tenants are not owned by a user, so orphans go after.
            session.execute(
                text("DELETE FROM users WHERE email LIKE :pattern"),
                {"pattern": f"%@{TEST_EMAIL_DOMAIN}"},
            )
            session.execute(
                text(
                    "DELETE FROM tenants t WHERE NOT EXISTS "
                    "(SELECT 1 FROM memberships m WHERE m.tenant_id = t.id)"
                )
            )
            session.commit()
    except sqlalchemy.exc.SQLAlchemyError:
        # No database in this environment; the tests that needed one skipped anyway.
        return
