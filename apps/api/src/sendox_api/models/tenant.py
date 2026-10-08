"""Workspaces — the tenancy boundary."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from sendox_api.models.base import Base, Timestamps, UUIDPrimaryKey


class Tenant(UUIDPrimaryKey, Timestamps, Base):
    """A brand workspace. Tenancy root, so it is not itself tenant-scoped."""

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")

    def __repr__(self) -> str:
        return f"<Tenant {self.slug}>"
