"""Add automatic download jobs.

Revision ID: a17d0b9c4e21
Revises: e60ae827ed98
Create Date: 2026-08-14 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a17d0b9c4e21"
down_revision: str | None = "e60ae827ed98"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "automation_job",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_key", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("movie_id", sa.UUID(), nullable=True),
        sa.Column("show_id", sa.UUID(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("selected_result_id", sa.UUID(), nullable=True),
        sa.Column("selected_release_title", sa.Text(), nullable=True),
        sa.Column("torrent_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(kind = 'movie' AND movie_id IS NOT NULL AND show_id IS NULL) OR "
            "(kind = 'show' AND show_id IS NOT NULL AND movie_id IS NULL)",
            name="ck_automation_job_target",
        ),
        sa.ForeignKeyConstraint(
            ["movie_id"],
            ["movie.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["selected_result_id"],
            ["indexer_query_result.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["show_id"],
            ["show.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["torrent_id"],
            ["torrent.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_key"),
    )
    op.create_index(
        "ix_automation_job_due",
        "automation_job",
        ["status", "next_attempt_at"],
        unique=False,
    )
    op.create_index(
        "ix_automation_job_movie_id",
        "automation_job",
        ["movie_id"],
        unique=False,
    )
    op.create_index(
        "ix_automation_job_show_id",
        "automation_job",
        ["show_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_automation_job_show_id", table_name="automation_job")
    op.drop_index("ix_automation_job_movie_id", table_name="automation_job")
    op.drop_index("ix_automation_job_due", table_name="automation_job")
    op.drop_table("automation_job")
