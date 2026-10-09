"""Workspace activity log (scope M1 FE-7).

Writes go through the tenant-scoped session, so an audit entry can only ever be
recorded against the workspace the caller is acting in.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from sendox_api.models import AuditLog


def record(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    action: str,
    actor_user_id: uuid.UUID | None = None,
    target: str | None = None,
    meta: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        target=target,
        meta=meta or {},
    )
    session.add(entry)
    return entry
