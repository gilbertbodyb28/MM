from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from media_manager.database import Base
from media_manager.recommendations.schemas import utc_now


class TraktConnection(Base):
    __tablename__ = "trakt_connection"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    access_token: Mapped[str] = mapped_column(String(4096))
    refresh_token: Mapped[str | None] = mapped_column(String(4096))
    token_type: Mapped[str] = mapped_column(String(32), default="bearer")
    scope: Mapped[str | None] = mapped_column(String(500))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    account_username: Mapped[str | None] = mapped_column(String(320))
    account_slug: Mapped[str | None] = mapped_column(String(320))
    trakt_user_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )
