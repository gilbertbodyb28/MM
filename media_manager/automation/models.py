from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from media_manager.database import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AutomationJob(Base):
    __tablename__ = "automation_job"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'movie' AND movie_id IS NOT NULL AND show_id IS NULL "
            "AND episode_id IS NULL) OR "
            "(kind = 'show' AND show_id IS NOT NULL AND movie_id IS NULL "
            "AND episode_id IS NULL) OR "
            "(kind = 'episode' AND show_id IS NOT NULL AND episode_id IS NOT NULL "
            "AND movie_id IS NULL)",
            name="ck_automation_job_target",
        ),
        Index(
            "ix_automation_job_due",
            "status",
            "next_attempt_at",
        ),
        Index("ix_automation_job_movie_id", "movie_id"),
        Index("ix_automation_job_show_id", "show_id"),
        Index("ix_automation_job_episode_id", "episode_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    movie_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("movie.id", ondelete="CASCADE"),
        nullable=True,
    )
    show_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("show.id", ondelete="CASCADE"),
        nullable=True,
    )
    episode_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("episode.id", ondelete="CASCADE"),
        nullable=True,
    )

    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
    )
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    selected_result_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("indexer_query_result.id", ondelete="SET NULL"),
        nullable=True,
    )
    selected_release_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    torrent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("torrent.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
