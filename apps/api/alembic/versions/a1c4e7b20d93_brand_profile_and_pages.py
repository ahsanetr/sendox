"""brand profile and extracted pages

Revision ID: a1c4e7b20d93
Revises: 6c22d20629f9
Create Date: 2026-10-12 16:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1c4e7b20d93"
down_revision: str | None = "6c22d20629f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "sendox_app"
TENANT_SETTING = "app.current_tenant_id"
TENANT_PREDICATE = f"tenant_id = NULLIF(current_setting('{TENANT_SETTING}', true), '')::uuid"

TABLES = ("brand_profiles", "brand_pages")


def upgrade() -> None:
    brand_tone = postgresql.ENUM(
        "warm", "playful", "direct", "luxury", "technical", name="brand_tone"
    )
    brand_tone.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "brand_profiles",
        sa.Column("what_you_sell", sa.Text(), nullable=True),
        sa.Column("audience", sa.Text(), nullable=True),
        sa.Column(
            "tone",
            postgresql.ENUM(
                "warm",
                "playful",
                "direct",
                "luxury",
                "technical",
                name="brand_tone",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("never_say", sa.Text(), nullable=True),
        sa.Column("voice_notes", sa.Text(), nullable=True),
        sa.Column("logo_url", sa.String(length=2048), nullable=True),
        sa.Column("brand_colors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_brand_profile_tenant"),
    )
    op.create_index(
        op.f("ix_brand_profiles_tenant_id"), "brand_profiles", ["tenant_id"], unique=False
    )

    op.create_table(
        "brand_pages",
        sa.Column("store_id", sa.UUID(), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("images", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("excluded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("crawled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["store_id"], ["shopify_stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "url", name="uq_brand_page_tenant_url"),
    )
    op.create_index(op.f("ix_brand_pages_store_id"), "brand_pages", ["store_id"], unique=False)
    op.create_index(op.f("ix_brand_pages_tenant_id"), "brand_pages", ["tenant_id"], unique=False)

    # A brand profile is a merchant's own words about their business, and the
    # extracted pages are their storefront copy. Neither is catastrophic to leak
    # the way an access token is, but the rule here is not graded by severity:
    # every tenant-scoped table gets the same FORCE'd policy, and
    # tests/test_rls.py enumerates the models and fails if one is missed.
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({TENANT_PREDICATE}) WITH CHECK ({TENANT_PREDICATE})"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_index(op.f("ix_brand_pages_tenant_id"), table_name="brand_pages")
    op.drop_index(op.f("ix_brand_pages_store_id"), table_name="brand_pages")
    op.drop_table("brand_pages")
    op.drop_index(op.f("ix_brand_profiles_tenant_id"), table_name="brand_profiles")
    op.drop_table("brand_profiles")
    postgresql.ENUM(name="brand_tone").drop(op.get_bind(), checkfirst=True)
