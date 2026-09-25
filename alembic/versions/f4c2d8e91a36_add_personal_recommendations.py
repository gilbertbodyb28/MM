"""add personal recommendations

Revision ID: f4c2d8e91a36
Revises: a17d0b9c4e21
Create Date: 2026-08-14 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f4c2d8e91a36"
down_revision: str | None = "a17d0b9c4e21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recommendation_user_mapping",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("tautulli_user_id", sa.String(length=128), nullable=True),
        sa.Column("plex_account_id", sa.String(length=128), nullable=True),
        sa.Column("plex_username", sa.String(length=320), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("plex_account_id"),
        sa.UniqueConstraint("tautulli_user_id"),
    )
    op.create_table(
        "watch_history_item",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("media_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("series_title", sa.String(length=500), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("genres", sa.JSON(), nullable=False),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("watched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("watch_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("completion_percent", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "source",
            "source_event_id",
            name="uq_watch_history_user_source_event",
        ),
    )
    op.create_index(
        "ix_watch_history_item_user_id",
        "watch_history_item",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_watch_history_user_watched_at",
        "watch_history_item",
        ["user_id", "watched_at"],
        unique=False,
    )
    op.create_table(
        "media_recommendation",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("media_type", sa.String(length=32), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("external_id", sa.Integer(), nullable=True),
        sa.Column("metadata_provider", sa.String(length=32), nullable=True),
        sa.Column("poster_path", sa.String(length=2048), nullable=True),
        sa.Column("vote_average", sa.Float(), nullable=True),
        sa.Column("overview", sa.String(length=5000), nullable=True),
        sa.Column("added", sa.Boolean(), nullable=False),
        sa.Column("media_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.String(length=800), nullable=False),
        sa.Column("genres", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "rank",
            name="uq_media_recommendation_user_rank",
        ),
    )
    op.create_index(
        "ix_media_recommendation_user_id",
        "media_recommendation",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_media_recommendation_user_generated_at",
        "media_recommendation",
        ["user_id", "generated_at"],
        unique=False,
    )
    op.create_table(
        "recommendation_sync_state",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("last_cursor", sa.String(length=128), nullable=True),
        sa.Column(
            "last_sync_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_sync_completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("last_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("refresh_lease_id", sa.UUID(), nullable=True),
        sa.Column(
            "refresh_lease_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "source",
            name="uq_recommendation_sync_user_source",
        ),
    )
    op.create_index(
        "ix_recommendation_sync_state_user_id",
        "recommendation_sync_state",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recommendation_sync_state_user_id",
        table_name="recommendation_sync_state",
    )
    op.drop_table("recommendation_sync_state")
    op.drop_index(
        "ix_media_recommendation_user_generated_at",
        table_name="media_recommendation",
    )
    op.drop_index(
        "ix_media_recommendation_user_id",
        table_name="media_recommendation",
    )
    op.drop_table("media_recommendation")
    op.drop_index(
        "ix_watch_history_user_watched_at",
        table_name="watch_history_item",
    )
    op.drop_index(
        "ix_watch_history_item_user_id",
        table_name="watch_history_item",
    )
    op.drop_table("watch_history_item")
    op.drop_table("recommendation_user_mapping")
