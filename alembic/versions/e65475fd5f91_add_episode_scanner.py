"""Add the hourly episode scanner settings, runs and results.

Revision ID: e65475fd5f91
Revises: 5d7e9a1b3c40
Create Date: 2026-09-25 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e65475fd5f91"
down_revision: str | None = "5d7e9a1b3c40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    settings = op.create_table(
        "episode_scan_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_episode_scan_settings_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    # The scanner is what the owner asked for, so it starts enabled; the UI
    # switch turns it off.
    op.bulk_insert(settings, [{"id": 1, "enabled": True}])

    op.create_table(
        "episode_scan_run",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shows_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("shows_checked", sa.Integer(), server_default="0", nullable=False),
        sa.Column("shows_failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("episodes_found", sa.Integer(), server_default="0", nullable=False),
        sa.Column("episodes_sent", sa.Integer(), server_default="0", nullable=False),
        sa.Column("episodes_skipped", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "episodes_not_found", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("errors", sa.Integer(), server_default="0", nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_episode_scan_run_started_at",
        "episode_scan_run",
        ["started_at"],
        unique=False,
    )
    op.create_index(
        "uq_episode_scan_run_single_running",
        "episode_scan_run",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )

    op.create_table(
        "episode_scan_item",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("show_id", sa.UUID(), nullable=True),
        sa.Column("episode_id", sa.UUID(), nullable=True),
        sa.Column("show_name", sa.Text(), nullable=True),
        sa.Column("season_number", sa.Integer(), nullable=True),
        sa.Column("episode_number", sa.Integer(), nullable=True),
        sa.Column("episode_title", sa.Text(), nullable=True),
        sa.Column("air_date", sa.Date(), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column("release_title", sa.Text(), nullable=True),
        sa.Column("indexer", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["episode_scan_run.id"],
            name="fk_episode_scan_item_run_id_episode_scan_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["show_id"],
            ["show.id"],
            name="fk_episode_scan_item_show_id_show",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["episode_id"],
            ["episode.id"],
            name="fk_episode_scan_item_episode_id_episode",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_episode_scan_item_run_id",
        "episode_scan_item",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_episode_scan_item_outcome_created_at",
        "episode_scan_item",
        ["outcome", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_episode_scan_item_outcome_created_at",
        table_name="episode_scan_item",
    )
    op.drop_index("ix_episode_scan_item_run_id", table_name="episode_scan_item")
    op.drop_table("episode_scan_item")
    op.drop_index(
        "uq_episode_scan_run_single_running",
        table_name="episode_scan_run",
        postgresql_where=sa.text("status = 'running'"),
    )
    op.drop_index("ix_episode_scan_run_started_at", table_name="episode_scan_run")
    op.drop_table("episode_scan_run")
    op.drop_table("episode_scan_settings")
