from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from media_manager.database import Base
from media_manager.recommendations.schemas import utc_now


class RecommendationUserMapping(Base):
    __tablename__ = "recommendation_user_mapping"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tautulli_user_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    plex_account_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    plex_username: Mapped[str | None] = mapped_column(String(320))
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class WatchHistoryItem(Base):
    __tablename__ = "watch_history_item"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "source",
            "source_event_id",
            name="uq_watch_history_user_source_event",
        ),
        Index("ix_watch_history_user_watched_at", "user_id", "watched_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"),
        index=True,
    )
    source: Mapped[str] = mapped_column(String(32))
    source_event_id: Mapped[str] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(32), default="watch")
    media_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(500))
    series_title: Mapped[str | None] = mapped_column(String(500))
    year: Mapped[int | None]
    genres: Mapped[list[str]] = mapped_column(JSON, default=list)
    rating: Mapped[float | None] = mapped_column(Float)
    watched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    watch_duration_seconds: Mapped[int | None]
    completion_percent: Mapped[float | None] = mapped_column(Float)
    external_ids: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )


class MediaRecommendation(Base):
    __tablename__ = "media_recommendation"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "rank",
            name="uq_media_recommendation_user_rank",
        ),
        Index(
            "ix_media_recommendation_user_generated_at",
            "user_id",
            "generated_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300))
    media_type: Mapped[str] = mapped_column(String(32))
    year: Mapped[int | None]
    external_id: Mapped[int | None]
    metadata_provider: Mapped[str | None] = mapped_column(String(32))
    poster_path: Mapped[str | None] = mapped_column(String(2_048))
    vote_average: Mapped[float | None] = mapped_column(Float)
    overview: Mapped[str | None] = mapped_column(String(5_000))
    added: Mapped[bool] = mapped_column(default=False)
    media_id: Mapped[UUID | None] = mapped_column(nullable=True)
    reason: Mapped[str] = mapped_column(String(800))
    genres: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float)
    rank: Mapped[int]
    model_name: Mapped[str] = mapped_column(String(200))
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RecommendationSyncState(Base):
    __tablename__ = "recommendation_sync_state"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "source",
            name="uq_recommendation_sync_user_source",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"),
        index=True,
    )
    source: Mapped[str] = mapped_column(String(32))
    last_cursor: Mapped[str | None] = mapped_column(String(128))
    last_sync_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_sync_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
    refresh_lease_id: Mapped[UUID | None] = mapped_column(nullable=True)
    refresh_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class RecommendationSection(Base):
    __tablename__ = "recommendation_section"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "rank",
            name="uq_recommendation_section_user_rank",
        ),
        Index(
            "ix_recommendation_section_user_generated_at",
            "user_id",
            "generated_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"),
        index=True,
    )
    source_title: Mapped[str] = mapped_column(String(500))
    source_media_type: Mapped[str] = mapped_column(String(32))
    source_year: Mapped[int | None]
    source_external_ids: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    source_genres: Mapped[list[str]] = mapped_column(JSON, default=list)
    reason: Mapped[str] = mapped_column(String(800))
    rank: Mapped[int]
    candidates_considered: Mapped[int] = mapped_column(default=0)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    items: Mapped[list["RecommendationSectionItem"]] = relationship(
        back_populates="section",
        cascade="all, delete-orphan",
        order_by="RecommendationSectionItem.rank",
    )


class RecommendationSectionItem(Base):
    __tablename__ = "recommendation_section_item"
    __table_args__ = (
        UniqueConstraint(
            "section_id",
            "rank",
            name="uq_recommendation_section_item_rank",
        ),
        UniqueConstraint(
            "section_id",
            "media_type",
            "external_id",
            name="uq_recommendation_section_item_external",
        ),
        Index(
            "ix_recommendation_section_item_external",
            "media_type",
            "external_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    section_id: Mapped[UUID] = mapped_column(
        ForeignKey("recommendation_section.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300))
    media_type: Mapped[str] = mapped_column(String(32))
    year: Mapped[int | None]
    external_id: Mapped[int]
    metadata_provider: Mapped[str] = mapped_column(String(32), default="tmdb")
    poster_path: Mapped[str | None] = mapped_column(String(2_048))
    added: Mapped[bool] = mapped_column(default=False)
    media_id: Mapped[UUID | None] = mapped_column(nullable=True)
    score: Mapped[float] = mapped_column(Float)
    rank: Mapped[int]
    section: Mapped[RecommendationSection] = relationship(back_populates="items")
