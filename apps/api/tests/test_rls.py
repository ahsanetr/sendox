"""Tenant isolation is enforced by Postgres, and these tests prove it.

This is the phase 0.2 exit criterion: a cross-tenant read must come back empty,
not merely be absent from the queries we happened to write.

Marked `integration` because real policies need a real Postgres.
"""

import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from sendox_api.config import Settings
from sendox_api.db import (
    current_tenant,
    get_sessionmaker,
    global_session,
    session_role,
    tenant_session,
)
from sendox_api.models import AuditLog, Base, MemberRole, Membership, Tenant, TenantScoped, User

pytestmark = pytest.mark.integration


def _database_up(settings: Settings) -> bool:
    try:
        with get_sessionmaker(settings)() as session:
            session.execute(text("SELECT 1"))
        return True
    except sqlalchemy.exc.SQLAlchemyError:
        return False


@pytest.fixture
def db(settings: Settings) -> Settings:
    if not _database_up(settings):
        pytest.skip("Postgres not running — start it with `make up`")
    return settings


@pytest.fixture
def two_tenants(db: Settings) -> Iterator[tuple[Tenant, Tenant, User]]:
    """Two workspaces and one user, cleaned up afterwards."""
    suffix = uuid.uuid4().hex[:8]
    with global_session(db) as session:
        alpha = Tenant(name="Alpha Brand", slug=f"alpha-{suffix}")
        beta = Tenant(name="Beta Brand", slug=f"beta-{suffix}")
        user = User(email=f"owner-{suffix}@example.test", full_name="Test Owner")
        session.add_all([alpha, beta, user])
        session.flush()
        ids = (alpha.id, beta.id, user.id)

    with global_session(db) as session:
        yield (
            session.get(Tenant, ids[0]),  # type: ignore[arg-type]
            session.get(Tenant, ids[1]),  # type: ignore[arg-type]
            session.get(User, ids[2]),  # type: ignore[arg-type]
        )

    # Tenant delete cascades to memberships and audit logs.
    with global_session(db) as session:
        for tenant_id in ids[:2]:
            tenant = session.get(Tenant, tenant_id)
            if tenant:
                session.delete(tenant)
        leftover = session.get(User, ids[2])
        if leftover:
            session.delete(leftover)


def _log_count(session: Session) -> int:
    return session.execute(select(func.count()).select_from(AuditLog)).scalar_one()


def test_application_sessions_are_not_superuser(db: Settings) -> None:
    """The precondition for every other test in this file.

    Postgres skips row-level security for superusers, so if a session ever runs as
    one, the policies below are decorative and the isolation tests pass vacuously.
    """
    with global_session(db) as session:
        role, is_superuser = session_role(session)

    assert role == db.db_app_role
    assert not is_superuser, "RLS is bypassed for superusers — isolation is NOT enforced"


def test_every_tenant_scoped_model_has_an_rls_policy(db: Settings) -> None:
    """A new tenant-scoped table must not reach production unprotected."""
    scoped = {
        mapper.class_.__tablename__
        for mapper in Base.registry.mappers
        if issubclass(mapper.class_, TenantScoped)
    }

    with global_session(db) as session:
        protected = set(
            session.execute(
                text(
                    "SELECT c.relname FROM pg_class c "
                    "JOIN pg_policy p ON p.polrelid = c.oid "
                    "WHERE c.relrowsecurity AND c.relforcerowsecurity"
                )
            )
            .scalars()
            .all()
        )

    assert scoped, "no tenant-scoped models found — the test would pass vacuously"
    assert scoped <= protected, f"missing RLS policy on: {sorted(scoped - protected)}"


def test_a_tenant_sees_only_its_own_rows(
    db: Settings, two_tenants: tuple[Tenant, Tenant, User]
) -> None:
    alpha, beta, user = two_tenants

    with tenant_session(db, alpha.id) as session:
        session.add(AuditLog(tenant_id=alpha.id, actor_user_id=user.id, action="alpha.one"))
        session.add(AuditLog(tenant_id=alpha.id, actor_user_id=user.id, action="alpha.two"))

    with tenant_session(db, beta.id) as session:
        session.add(AuditLog(tenant_id=beta.id, actor_user_id=user.id, action="beta.one"))

    with tenant_session(db, alpha.id) as session:
        assert current_tenant(session) == alpha.id
        actions = set(session.execute(select(AuditLog.action)).scalars().all())
        assert actions == {"alpha.one", "alpha.two"}
        assert _log_count(session) == 2

    with tenant_session(db, beta.id) as session:
        actions = set(session.execute(select(AuditLog.action)).scalars().all())
        assert actions == {"beta.one"}


def test_explicitly_querying_another_tenant_id_returns_nothing(
    db: Settings, two_tenants: tuple[Tenant, Tenant, User]
) -> None:
    """Even a deliberate cross-tenant filter is blocked by the policy."""
    alpha, beta, user = two_tenants

    with tenant_session(db, beta.id) as session:
        session.add(AuditLog(tenant_id=beta.id, actor_user_id=user.id, action="beta.secret"))

    with tenant_session(db, alpha.id) as session:
        rows = (
            session.execute(select(AuditLog).where(AuditLog.tenant_id == beta.id)).scalars().all()
        )
        assert rows == []


def test_writing_a_row_for_another_tenant_is_refused(
    db: Settings, two_tenants: tuple[Tenant, Tenant, User]
) -> None:
    """WITH CHECK stops a mislabelled insert, not just a bad read."""
    alpha, beta, user = two_tenants

    with (
        pytest.raises(sqlalchemy.exc.ProgrammingError) as caught,
        tenant_session(db, alpha.id) as session,
    ):
        session.add(AuditLog(tenant_id=beta.id, actor_user_id=user.id, action="smuggled"))

    assert "row-level security" in str(caught.value).lower()

    with tenant_session(db, beta.id) as session:
        assert _log_count(session) == 0


def test_session_without_tenant_context_sees_no_tenant_rows(
    db: Settings, two_tenants: tuple[Tenant, Tenant, User]
) -> None:
    alpha, _beta, user = two_tenants

    with tenant_session(db, alpha.id) as session:
        session.add(AuditLog(tenant_id=alpha.id, actor_user_id=user.id, action="alpha.only"))

    with global_session(db) as session:
        assert current_tenant(session) is None
        # Globally-scoped tables stay readable...
        assert session.get(Tenant, alpha.id) is not None
        # ...while tenant-scoped ones are invisible.
        assert _log_count(session) == 0


def test_memberships_are_isolated_too(
    db: Settings, two_tenants: tuple[Tenant, Tenant, User]
) -> None:
    alpha, beta, user = two_tenants

    for tenant in (alpha, beta):
        with tenant_session(db, tenant.id) as session:
            session.add(Membership(tenant_id=tenant.id, user_id=user.id, role=MemberRole.OWNER))

    with tenant_session(db, alpha.id) as session:
        rows = session.execute(select(Membership)).scalars().all()
        assert [row.tenant_id for row in rows] == [alpha.id]
        assert rows[0].role is MemberRole.OWNER
