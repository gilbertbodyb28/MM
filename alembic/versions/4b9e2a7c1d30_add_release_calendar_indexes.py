"""Add movie release dates and release-calendar indexes.

Revision ID: 4b9e2a7c1d30
Revises: c7f1e6a24b90
Create Date: 2026-08-14 20:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4b9e2a7c1d30"
down_revision: str | None = "c7f1e6a24b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("movie", sa.Column("release_date", sa.Date(), nullable=True))
    op.create_index(
        "ix_movie_release_date",
        "movie",
        ["release_date"],
        unique=False,
    )
    op.create_index(
        "ix_episode_air_date",
        "episode",
        ["air_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_episode_air_date", table_name="episode")
    op.drop_index("ix_movie_release_date", table_name="movie")
    op.drop_column("movie", "release_date")
