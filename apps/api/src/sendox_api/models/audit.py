"""Workspace activity log (scope M1 FE-7).

Present from 0.2 because it is the simplest genuinely tenant-scoped table, which
makes it the thing the row-level security tests exercise.
"""

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from sendox_api.models.base import Base, TenantScoped, Timestamps, UUIDPrimaryKey


class AuditLog(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    __tablename__ = "audit_logs"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    target: Mapped[str | None] = mapped_column(String(200), nullable=True)
    meta: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
