"""Database engine, sessions, and the tenant-isolation contract.

Row-level security is enforced in Postgres, not in application code: every
tenant-scoped table has a policy comparing `tenant_id` against the
`app.current_tenant_id` session setting. A query that forgets to filter by tenant
returns nothing rather than another brand's data.

`tenant_session` is therefore the only correct way to touch tenant-scoped tables.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from uuid import UUID

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from sendox_api.config import Settings

TENANT_SETTING = "app.current_tenant_id"
USER_SETTING = "app.current_user_id"


@lru_cache
def _engine_for(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True, future=True)


def get_engine(settings: Settings) -> Engine:
    return _engine_for(settings.database_url)


@lru_cache
def _sessionmaker_for(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=_engine_for(database_url), expire_on_commit=False)


def get_sessionmaker(settings: Settings) -> sessionmaker[Session]:
    return _sessionmaker_for(settings.database_url)


def _assume_app_role(session: Session, settings: Settings) -> None:
    """Switch to the non-superuser application role.

    The connection role owns the schema and (under the postgres Docker image) is
    the bootstrap superuser, for whom row-level security is skipped entirely.
    Switching roles is what makes the policies bite. LOCAL scopes it to the
    transaction, so a pooled connection never carries the role into a later one.

    The role name is an identifier, not a value, so it cannot be bound as a
    parameter; it is validated instead.
    """
    role = settings.db_app_role
    if not role.replace("_", "").isalnum():
        raise ValueError(f"unsafe db_app_role: {role!r}")
    session.execute(text(f"SET LOCAL ROLE {role}"))


def _set_context(
    session: Session, *, tenant_id: UUID | None = None, user_id: UUID | None = None
) -> None:
    """Publish who is asking and which workspace they are in.

    Policies read both. is_local=true scopes each setting to the current
    transaction, so a pooled connection can never leak one request's context into
    the next.
    """
    for key, value in ((TENANT_SETTING, tenant_id), (USER_SETTING, user_id)):
        session.execute(
            text("SELECT set_config(:key, :value, true)"),
            {"key": key, "value": str(value) if value else ""},
        )


def adopt_tenant(session: Session, tenant_id: UUID, user_id: UUID | None = None) -> None:
    """Switch an already-open session into a workspace's context mid-transaction.

    Needed for exactly one situation: creating a workspace. The owner's membership
    row cannot be inserted without tenant context — the policy's WITH CHECK
    rejects it — yet the context cannot be set before the workspace has an id.
    Setting it between the two inserts resolves that without exempting the insert
    from row-level security.

    Safe because the underlying set_config is transaction-local: the context ends
    when this transaction does and cannot leak into the next request on a pooled
    connection.
    """
    _set_context(session, tenant_id=tenant_id, user_id=user_id)


@contextmanager
def tenant_session(
    settings: Settings, tenant_id: UUID, user_id: UUID | None = None
) -> Iterator[Session]:
    """A session that can only see one workspace's rows."""
    with get_sessionmaker(settings)() as session:
        _assume_app_role(session, settings)
        _set_context(session, tenant_id=tenant_id, user_id=user_id)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


@contextmanager
def user_session(settings: Settings, user_id: UUID) -> Iterator[Session]:
    """A session scoped to one person, across every workspace they belong to.

    Needed for the operations that are legitimately cross-tenant: listing the
    workspaces someone can switch between, and erasing an account. Rather than
    exempting those queries from row-level security, the database carries a second
    policy on `memberships` permitting a row whose user_id matches this context —
    so "you may see your own memberships" is enforced in Postgres, like everything
    else, instead of trusted to a WHERE clause.

    It grants no access to workspace *content*: only `memberships` has that policy.
    """
    with get_sessionmaker(settings)() as session:
        _assume_app_role(session, settings)
        _set_context(session, user_id=user_id)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


@contextmanager
def global_session(settings: Settings) -> Iterator[Session]:
    """A session with no tenant context.

    Correct for the globally-scoped tables (`tenants`, `users`) and for creating a
    workspace before it has an id to scope to. Tenant-scoped tables deliberately
    appear empty here — that is RLS working, not a bug.
    """
    with get_sessionmaker(settings)() as session:
        _assume_app_role(session, settings)
        _set_context(session)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def current_tenant(session: Session) -> UUID | None:
    """Read back the tenant context, for assertions and debugging."""
    return _read_uuid_setting(session, TENANT_SETTING)


def current_user_id(session: Session) -> UUID | None:
    return _read_uuid_setting(session, USER_SETTING)


def _read_uuid_setting(session: Session, key: str) -> UUID | None:
    raw = session.execute(text("SELECT current_setting(:key, true)"), {"key": key}).scalar()
    return UUID(raw) if raw else None


def session_role(session: Session) -> tuple[str, bool]:
    """The effective role and whether it is a superuser.

    If this ever reports a superuser, tenant isolation is not being enforced.
    """
    row = session.execute(
        text("SELECT current_user, (SELECT rolsuper FROM pg_roles WHERE rolname = current_user)")
    ).one()
    return str(row[0]), bool(row[1])
