"""One-time email tokens: address verification and password reset.

Not tenant-scoped — a user exists before any workspace does, and a reset link has
to work for someone who has been removed from every workspace.

Only the hash is stored, so a database leak cannot be replayed as a working link.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from sendox_api.models.base import Base, Timestamps, UUIDPrimaryKey
from sendox_api.security import TokenPurpose


class EmailToken(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "email_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[TokenPurpose] = mapped_column(
        SAEnum(
            TokenPurpose, name="email_token_purpose", values_callable=lambda e: [m.value for m in e]
        ),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
