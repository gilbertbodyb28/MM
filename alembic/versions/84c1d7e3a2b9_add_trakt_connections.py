"""Add per-user Trakt OAuth connections.

Revision ID: 84c1d7e3a2b9
Revises: 6e4f9b21a7d3
Create Date: 2026-08-17 16:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "84c1d7e3a2b9"
down_revision: str | None = "6e4f9b21a7d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trakt_connection",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("access_token", sa.String(length=4096), nullable=False),
        sa.Column("refresh_token", sa.String(length=4096), nullable=True),
        sa.Column("token_type", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("account_username", sa.String(length=320), nullable=True),
        sa.Column("account_slug", sa.String(length=320), nullable=True),
        sa.Column("trakt_user_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        "ix_trakt_connection_user_id",
        "trakt_connection",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_trakt_connection_user_id", table_name="trakt_connection")
    op.drop_table("trakt_connection")
