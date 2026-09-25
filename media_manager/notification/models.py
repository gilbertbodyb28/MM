from uuid import UUID

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from media_manager.database import Base


class Notification(Base):
    __tablename__ = "notification"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    message: Mapped[str]
    read: Mapped[bool]
    timestamp = mapped_column(DateTime, nullable=False)
