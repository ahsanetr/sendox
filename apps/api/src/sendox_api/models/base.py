"""Declarative base and shared column mixins."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """All models inherit from here; Alembic autogenerate reads this metadata."""


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantScoped:
    """Marks a table as belonging to exactly one workspace.

    Every table carrying this mixin must also have a row-level security policy;
    `tests/test_rls.py` enumerates them and fails if one is left unprotected.
    """

    if TYPE_CHECKING:
        # Supplied by the concrete model; declared here so code that enumerates
        # tenant-scoped tables type-checks.
        __tablename__: str

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
