from datetime import date

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from media_manager.movies.models import Movie, MovieFile
from media_manager.release_calendar.schemas import ReleaseCalendarItem
from media_manager.tv.models import Episode, EpisodeFile, Season, Show


class ReleaseCalendarRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_releases(
        self,
        start_date: date,
        end_date: date,
        media_type: str = "all",
    ) -> list[ReleaseCalendarItem]:
        releases: list[ReleaseCalendarItem] = []

        if media_type in {"all", "movie"}:
            downloaded = exists().where(MovieFile.movie_id == Movie.id)
            statement = (
                select(Movie, downloaded.label("available"))
                .where(
                    Movie.release_date.is_not(None),
                    Movie.release_date >= start_date,
                    Movie.release_date <= end_date,
                )
                .order_by(Movie.release_date, Movie.name)
            )
            for movie, available in (await self.db.execute(statement)).all():
                releases.append(
                    ReleaseCalendarItem(
                        id=movie.id,
                        media_type="movie",
                        media_id=movie.id,
                        poster_id=movie.id,
                        name=movie.name,
                        overview=movie.overview,
                        release_date=movie.release_date,
                        available=available,
                    )
                )

        if media_type in {"all", "episode"}:
            downloaded = exists().where(EpisodeFile.episode_id == Episode.id)
            statement = (
                select(Episode, Season, Show, downloaded.label("available"))
                .join(Season, Season.id == Episode.season_id)
                .join(Show, Show.id == Season.show_id)
                .where(
                    Episode.air_date.is_not(None),
                    Episode.air_date >= start_date,
                    Episode.air_date <= end_date,
                )
                .order_by(Episode.air_date, Show.name, Season.number, Episode.number)
            )
            for episode, season, show, available in (
                await self.db.execute(statement)
            ).all():
                releases.append(
                    ReleaseCalendarItem(
                        id=episode.id,
                        media_type="episode",
                        media_id=show.id,
                        poster_id=show.id,
                        season_id=season.id,
                        name=show.name,
                        episode_title=episode.title,
                        overview=episode.overview or show.overview,
                        release_date=episode.air_date,
                        season_number=season.number,
                        episode_number=episode.number,
                        available=available,
                    )
                )

        return sorted(
            releases,
            key=lambda item: (
                item.release_date,
                item.name.casefold(),
                item.season_number or -1,
                item.episode_number or -1,
            ),
        )
