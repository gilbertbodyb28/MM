"""Add grouped recommendations and external history identities.

Revision ID: 6e4f9b21a7d3
Revises: d2a6c4e8f901
Create Date: 2026-08-17 15:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "6e4f9b21a7d3"
down_revision: str | None = "d2a6c4e8f901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "watch_history_item",
        sa.Column("external_ids", sa.JSON(), server_default="{}", nullable=False),
    )
    op.create_table(
        "recommendation_section",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("source_title", sa.String(length=500), nullable=False),
        sa.Column("source_media_type", sa.String(length=32), nullable=False),
        sa.Column("source_year", sa.Integer(), nullable=True),
        sa.Column("source_external_ids", sa.JSON(), nullable=False),
        sa.Column("source_genres", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(length=800), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("candidates_considered", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "rank", name="uq_recommendation_section_user_rank"
        ),
    )
    op.create_index(
        "ix_recommendation_section_user_id",
        "recommendation_section",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_recommendation_section_user_generated_at",
        "recommendation_section",
        ["user_id", "generated_at"],
        unique=False,
    )
    op.create_table(
        "recommendation_section_item",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("section_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("media_type", sa.String(length=32), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("external_id", sa.Integer(), nullable=False),
        sa.Column("metadata_provider", sa.String(length=32), nullable=False),
        sa.Column("poster_path", sa.String(length=2048), nullable=True),
        sa.Column("added", sa.Boolean(), nullable=False),
        sa.Column("media_id", sa.UUID(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["section_id"], ["recommendation_section.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "section_id",
            "media_type",
            "external_id",
            name="uq_recommendation_section_item_external",
        ),
        sa.UniqueConstraint(
            "section_id", "rank", name="uq_recommendation_section_item_rank"
        ),
    )
    op.create_index(
        "ix_recommendation_section_item_section_id",
        "recommendation_section_item",
        ["section_id"],
        unique=False,
    )
    op.create_index(
        "ix_recommendation_section_item_external",
        "recommendation_section_item",
        ["media_type", "external_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recommendation_section_item_external",
        table_name="recommendation_section_item",
    )
    op.drop_index(
        "ix_recommendation_section_item_section_id",
        table_name="recommendation_section_item",
    )
    op.drop_table("recommendation_section_item")
    op.drop_index(
        "ix_recommendation_section_user_generated_at",
        table_name="recommendation_section",
    )
    op.drop_index(
        "ix_recommendation_section_user_id", table_name="recommendation_section"
    )
    op.drop_table("recommendation_section")
    op.drop_column("watch_history_item", "external_ids")
