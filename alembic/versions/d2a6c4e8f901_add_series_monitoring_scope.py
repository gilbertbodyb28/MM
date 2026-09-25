"""Add per-show and per-season monitoring scope.

Revision ID: d2a6c4e8f901
Revises: 4b9e2a7c1d30
Create Date: 2026-08-17 13:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d2a6c4e8f901"
down_revision: str | None = "4b9e2a7c1d30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "show",
        sa.Column(
            "monitor_scope",
            sa.String(length=16),
            server_default="entire",
            nullable=False,
        ),
    )
    op.add_column(
        "season",
        sa.Column(
            "monitored",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("season", "monitored")
    op.drop_column("show", "monitor_scope")
