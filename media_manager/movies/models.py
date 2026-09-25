from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, PrimaryKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from media_manager.common.models import MediaFileMixin, MediaMixin
from media_manager.database import Base


class Movie(Base, MediaMixin):
    __tablename__ = "movie"
    __table_args__ = (UniqueConstraint("external_id", "metadata_provider"),)

    release_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )


class MovieFile(Base, MediaFileMixin):
    __tablename__ = "movie_file"
    __table_args__ = (PrimaryKeyConstraint("movie_id", "file_path_suffix"),)

    movie_id: Mapped[UUID] = mapped_column(
        ForeignKey(column="movie.id", ondelete="CASCADE"),
    )

    torrent = relationship("Torrent", back_populates="movie_files", uselist=False)
