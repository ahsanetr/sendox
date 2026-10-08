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


def _set_tenant(session: Session, tenant_id: UUID | None) -> None:
    # is_local=true scopes the setting to the current transaction, so a pooled
    # connection can never leak one workspace's context into the next request.
    session.execute(
        text("SELECT set_config(:key, :value, true)"),
        {"key": TENANT_SETTING, "value": str(tenant_id) if tenant_id else ""},
    )


@contextmanager
def tenant_session(settings: Settings, tenant_id: UUID) -> Iterator[Session]:
    """A session that can only see one workspace's rows."""
    with get_sessionmaker(settings)() as session:
        _assume_app_role(session, settings)
        _set_tenant(session, tenant_id)
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
        _set_tenant(session, None)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def current_tenant(session: Session) -> UUID | None:
    """Read back the tenant context, for assertions and debugging."""
    raw = session.execute(
        text("SELECT current_setting(:key, true)"), {"key": TENANT_SETTING}
    ).scalar()
    return UUID(raw) if raw else None


def session_role(session: Session) -> tuple[str, bool]:
    """The effective role and whether it is a superuser.

    If this ever reports a superuser, tenant isolation is not being enforced.
    """
    row = session.execute(
        text("SELECT current_user, (SELECT rolsuper FROM pg_roles WHERE rolname = current_user)")
    ).one()
    return str(row[0]), bool(row[1])
