"""brand analyses

Revision ID: b7e2f9a41c08
Revises: a1c4e7b20d93
Create Date: 2026-10-15 14:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7e2f9a41c08"
down_revision: str | None = "a1c4e7b20d93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "sendox_app"
TENANT_SETTING = "app.current_tenant_id"
TENANT_PREDICATE = f"tenant_id = NULLIF(current_setting('{TENANT_SETTING}', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "brand_analyses",
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "version", name="uq_brand_analysis_tenant_version"),
    )
    op.create_index(
        op.f("ix_brand_analyses_tenant_id"), "brand_analyses", ["tenant_id"], unique=False
    )

    # An analysis quotes a brand's own copy back at it and records the prompt
    # that produced it. Same FORCE'd policy as every other tenant-scoped table;
    # tests/test_rls.py enumerates the models and fails if one is missed.
    op.execute("ALTER TABLE brand_analyses ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE brand_analyses FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON brand_analyses "
        f"USING ({TENANT_PREDICATE}) WITH CHECK ({TENANT_PREDICATE})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON brand_analyses TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON brand_analyses")
    op.drop_index(op.f("ix_brand_analyses_tenant_id"), table_name="brand_analyses")
    op.drop_table("brand_analyses")
