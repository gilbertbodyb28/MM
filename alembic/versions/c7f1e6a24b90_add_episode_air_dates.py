"""Add episode air dates.

Revision ID: c7f1e6a24b90
Revises: f4c2d8e91a36
Create Date: 2026-08-14 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7f1e6a24b90"
down_revision: str | None = "f4c2d8e91a36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "episode",
        sa.Column("air_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("episode", "air_date")
