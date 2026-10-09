"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Autogenerate emits postgresql.JSONB / postgresql.ENUM without importing the
# dialect, which fails at runtime inside the container rather than at review
# time. Importing it here means every generated migration has it. Ruff's unused
# import rule is waived for this file in pyproject.toml.
from sqlalchemy.dialects import postgresql  # noqa: F401

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
