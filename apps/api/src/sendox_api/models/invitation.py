"""Pending workspace invitations (scope M1 FE-5).

**Deliberately not row-level-security protected**, unlike every other table that
carries a tenant_id. An invitation has to be readable by its token *before* the
recipient belongs to the workspace — there is no tenant context to set yet, so an
RLS policy would hide the row from the one request that needs it.

The boundary instead comes from the token: 256 bits of entropy, stored hashed, and
every listing query filters by tenant_id explicitly. `test_invitations_are_scoped_
by_query` covers that.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from sendox_api.models.base import Base, Timestamps, UUIDPrimaryKey
from sendox_api.models.membership import MemberRole


class Invitation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "invitations"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_invitation_tenant_email"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[MemberRole] = mapped_column(
        SAEnum(MemberRole, name="member_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
