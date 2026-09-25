"""Add episode-targeted automatic search jobs.

Revision ID: 5d7e9a1b3c40
Revises: 84c1d7e3a2b9
Create Date: 2026-08-17 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5d7e9a1b3c40"
down_revision: str | None = "84c1d7e3a2b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_automation_job_target",
        "automation_job",
        type_="check",
    )
    op.add_column(
        "automation_job",
        sa.Column("episode_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_automation_job_episode_id_episode",
        "automation_job",
        "episode",
        ["episode_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_automation_job_episode_id",
        "automation_job",
        ["episode_id"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_automation_job_target",
        "automation_job",
        "(kind = 'movie' AND movie_id IS NOT NULL AND show_id IS NULL "
        "AND episode_id IS NULL) OR "
        "(kind = 'show' AND show_id IS NOT NULL AND movie_id IS NULL "
        "AND episode_id IS NULL) OR "
        "(kind = 'episode' AND show_id IS NOT NULL AND episode_id IS NOT NULL "
        "AND movie_id IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_automation_job_target",
        "automation_job",
        type_="check",
    )
    op.drop_index("ix_automation_job_episode_id", table_name="automation_job")
    op.drop_constraint(
        "fk_automation_job_episode_id_episode",
        "automation_job",
        type_="foreignkey",
    )
    op.drop_column("automation_job", "episode_id")
    op.create_check_constraint(
        "ck_automation_job_target",
        "automation_job",
        "(kind = 'movie' AND movie_id IS NOT NULL AND show_id IS NULL) OR "
        "(kind = 'show' AND show_id IS NOT NULL AND movie_id IS NULL)",
    )
