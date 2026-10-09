"""Build-status endpoint.

Serves the module manifest so the dashboard shows what is actually built rather
than what a document claims. The manifest ships with the package.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from sendox_api import __version__
from sendox_api.config import Settings
from sendox_api.db import global_session, session_role
from sendox_api.dependencies import SettingsDep
from sendox_api.models import Base, TenantScoped

router = APIRouter(prefix="/status", tags=["status"])

_MANIFEST_PATH = Path(__file__).resolve().parent.parent / "data" / "module_status.json"


@lru_cache
def _cached_manifest() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    return data


def _manifest(settings: Settings) -> dict[str, Any]:
    """Read the manifest, caching it only in production.

    The file changes whenever a phase lands, and a cached copy meant the status
    page kept reporting figures from whenever the server happened to start —
    which is exactly the drift this endpoint exists to prevent.
    """
    if settings.is_production:
        return _cached_manifest()
    fresh: dict[str, Any] = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    return fresh


@router.get("/modules", summary="What is built, by release and module")
async def modules(settings: SettingsDep) -> dict[str, Any]:
    manifest = _manifest(settings)

    counted = [*manifest["foundation"], *manifest["modules"]]
    tally: dict[str, int] = {}
    for item in counted:
        tally[item["status"]] = tally.get(item["status"], 0) + 1

    return {
        "api_version": __version__,
        "totals": {"items": len(counted), **tally},
        **manifest,
    }


@router.get("/database", summary="Schema, migration revision and tenant-isolation state")
async def database(settings: SettingsDep) -> dict[str, Any]:
    """Surfaces whether tenant isolation is actually in force.

    `enforced` is the honest answer to "is one brand's data safe from another's":
    every tenant-scoped table must have a FORCE'd policy *and* the session role
    must not be a superuser, because Postgres skips policies for superusers.
    """
    expected = sorted(
        mapper.class_.__tablename__
        for mapper in Base.registry.mappers
        if issubclass(mapper.class_, TenantScoped)
    )

    try:
        with global_session(settings) as session:
            role, is_superuser = session_role(session)
            revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
            tables = sorted(
                session.execute(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = 'public' ORDER BY tablename"
                    )
                )
                .scalars()
                .all()
            )
            protected = sorted(
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
    except Exception as exc:  # noqa: BLE001 - a status endpoint must not 500
        return {"reachable": False, "error": f"{type(exc).__name__}: {exc}"}

    unprotected = sorted(set(expected) - set(protected))

    return {
        "reachable": True,
        "migration_revision": revision,
        "session_role": role,
        "session_is_superuser": is_superuser,
        "tables": tables,
        "tenant_scoped_tables": expected,
        "rls_protected_tables": protected,
        "unprotected_tables": unprotected,
        "enforced": not is_superuser and not unprotected,
    }
