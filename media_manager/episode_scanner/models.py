from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from media_manager.database import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class EpisodeScanSettings(Base):
    """Singleton row holding the UI toggle for automatic scanning."""

    __tablename__ = "episode_scan_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_episode_scan_settings_singleton"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False, default=1)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )


class EpisodeScanRun(Base):
    __tablename__ = "episode_scan_run"
    __table_args__ = (
        Index("ix_episode_scan_run_started_at", "started_at"),
        # At most one scan may run at a time, across processes and workers.
        Index(
            "uq_episode_scan_run_single_running",
            "status",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    shows_total: Mapped[int] = mapped_column(default=0, nullable=False)
    shows_checked: Mapped[int] = mapped_column(default=0, nullable=False)
    shows_failed: Mapped[int] = mapped_column(default=0, nullable=False)
    episodes_found: Mapped[int] = mapped_column(default=0, nullable=False)
    episodes_sent: Mapped[int] = mapped_column(default=0, nullable=False)
    episodes_skipped: Mapped[int] = mapped_column(default=0, nullable=False)
    episodes_not_found: Mapped[int] = mapped_column(default=0, nullable=False)
    errors: Mapped[int] = mapped_column(default=0, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class EpisodeScanItem(Base):
    """One scanner decision about an episode, or a show-level problem."""

    __tablename__ = "episode_scan_item"
    __table_args__ = (
        Index("ix_episode_scan_item_run_id", "run_id"),
        Index("ix_episode_scan_item_outcome_created_at", "outcome", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("episode_scan_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The display fields are copied so history stays readable after a show is
    # deleted from the library.
    show_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("show.id", ondelete="SET NULL"),
        nullable=True,
    )
    episode_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("episode.id", ondelete="SET NULL"),
        nullable=True,
    )
    show_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    season_number: Mapped[int | None] = mapped_column(nullable=True)
    episode_number: Mapped[int | None] = mapped_column(nullable=True)
    episode_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    air_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    release_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexer: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
