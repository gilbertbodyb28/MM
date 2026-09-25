from datetime import date

from sqlalchemy import distinct, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from media_manager.common.repository import BaseRepository, EntityId
from media_manager.exceptions import ConflictError, NotFoundError
from media_manager.torrent.models import Torrent as TorrentModel
from media_manager.torrent.schemas import Torrent as TorrentSchema
from media_manager.torrent.schemas import TorrentId
from media_manager.tv import log
from media_manager.tv.models import Episode, EpisodeFile, Season, Show
from media_manager.tv.schemas import Episode as EpisodeSchema
from media_manager.tv.schemas import EpisodeFile as EpisodeFileSchema
from media_manager.tv.schemas import (
    EpisodeFileState,
    EpisodeId,
    EpisodeNumber,
    MonitorScope,
    SeasonId,
    SeasonNumber,
    ShowId,
)
from media_manager.tv.schemas import Season as SeasonSchema
from media_manager.tv.schemas import Show as ShowSchema


def _load_show_tree():  # noqa: ANN202
    return selectinload(Show.seasons).selectinload(Season.episodes)


class TvRepository(BaseRepository[Show, ShowSchema]):
    """
    Repository for managing TV shows, seasons, and episodes in the database.
    Provides methods to retrieve, save, and delete shows and seasons.
    """

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, Show, ShowSchema)

    async def get_by_external_id(
        self, external_id: int, metadata_provider: str
    ) -> ShowSchema:
        """Use the eager-loaded show query required by the nested schema.

        ``BaseMetadataService.check_if_exists`` calls the generic repository
        method.  The base implementation only loads the ``Show`` row, so
        serializing ``ShowSchema.seasons`` attempts an async lazy load and
        raises ``MissingGreenlet``.  Keep the generic entry point polymorphic
        while reusing the repository's complete show-tree query.
        """
        return await self.get_show_by_external_id(
            external_id=external_id,
            metadata_provider=metadata_provider,
        )

    async def get_show_by_id(self, show_id: ShowId) -> ShowSchema:
        try:
            stmt = select(Show).where(Show.id == show_id).options(_load_show_tree())
            result = (await self.db.execute(stmt)).unique().scalar_one_or_none()
            if not result:
                msg = f"Show with id {show_id} not found."
                raise NotFoundError(msg)
        except SQLAlchemyError:
            log.exception(f"Database error while retrieving show {show_id}")
            raise
        else:
            return ShowSchema.model_validate(result)

    async def get_show_by_external_id(
        self, external_id: int, metadata_provider: str
    ) -> ShowSchema:
        try:
            stmt = (
                select(Show)
                .where(Show.external_id == external_id)
                .where(Show.metadata_provider == metadata_provider)
                .options(_load_show_tree())
            )
            result = (await self.db.execute(stmt)).unique().scalar_one_or_none()
            if not result:
                msg = f"Show with external_id {external_id} and provider {metadata_provider} not found."
                raise NotFoundError(msg)
        except SQLAlchemyError:
            log.exception(
                f"Database error while retrieving show by external_id {external_id}",
            )
            raise
        else:
            return ShowSchema.model_validate(result)

    async def get_shows(self) -> list[ShowSchema]:
        try:
            stmt = select(Show).options(_load_show_tree())
            results = (await self.db.execute(stmt)).scalars().unique().all()
        except SQLAlchemyError:
            log.exception("Database error while retrieving all shows")
            raise
        else:
            return [ShowSchema.model_validate(show) for show in results]

    async def get_continuous_download_shows(self) -> list[ShowSchema]:
        """Return active shows opted into automatic future episode downloads."""
        try:
            stmt = (
                select(Show)
                .where(Show.continuous_download.is_(True))
                .options(_load_show_tree())
            )
            results = (await self.db.execute(stmt)).scalars().unique().all()
        except SQLAlchemyError:
            log.exception("Database error retrieving continuous-download shows")
            raise
        return [ShowSchema.model_validate(show) for show in results]

    async def delete_show(self, entity_id: EntityId) -> None:
        await self.delete(entity_id)

    async def set_show_library(self, entity_id: EntityId, library: str) -> None:
        await self.set_library(entity_id, library)

    async def get_total_downloaded_episodes_count(self) -> int:
        try:
            stmt = (
                select(func.count(distinct(Episode.id)))
                .select_from(Episode)
                .join(EpisodeFile)
            )
            result = (await self.db.execute(stmt)).scalar_one_or_none()
        except SQLAlchemyError:
            log.exception("Database error while calculating downloaded episodes count")
            raise
        else:
            return result or 0

    async def save_show(self, show: ShowSchema) -> ShowSchema:
        db_show = await self.db.get(Show, show.id) if show.id else None

        if db_show:  # Use base for update
            await self.save_media_base(
                media_schema=show, model_class=Show, exclude={"seasons", "episodes"}
            )
            # save_media_base returns a non-eager-loaded schema; reload with
            # selectinload so ShowSchema.seasons/episodes don't lazy-load.
            return await self.get_show_by_id(db_show.id)

        # Custom insertion for nested seasons/episodes
        db_show = Show(
            id=show.id,
            external_id=show.external_id,
            metadata_provider=show.metadata_provider,
            name=show.name,
            overview=show.overview,
            year=show.year,
            ended=show.ended,
            original_language=show.original_language,
            imdb_id=show.imdb_id,
            continuous_download=show.continuous_download,
            monitor_scope=show.monitor_scope.value,
            library=show.library,
            seasons=[
                Season(
                    id=season.id,
                    show_id=show.id,
                    number=season.number,
                    external_id=season.external_id,
                    name=season.name,
                    overview=season.overview,
                    monitored=season.monitored,
                    episodes=[
                        Episode(
                            id=episode.id,
                            season_id=season.id,
                            number=episode.number,
                            external_id=episode.external_id,
                            title=episode.title,
                            overview=episode.overview,
                            air_date=episode.air_date,
                        )
                        for episode in season.episodes
                    ],
                )
                for season in show.seasons
            ],
        )
        self.db.add(db_show)
        try:
            await self.db.commit()
            await self.db.refresh(db_show, ["seasons"])
        except IntegrityError as e:
            await self.db.rollback()
            msg = f"Integrity error: {e.orig}"
            raise ConflictError(msg) from e
        except SQLAlchemyError:
            await self.db.rollback()
            raise
        else:
            # AsyncSession forbids implicit lazy loads after commit; reload eagerly.
            return await self.get_show_by_id(db_show.id)

    async def get_season(self, season_id: SeasonId) -> SeasonSchema:
        season = await self.db.get(
            Season, season_id, options=[selectinload(Season.episodes)]
        )
        if not season:
            msg = f"Season {season_id} not found"
            raise NotFoundError(msg)
        return SeasonSchema.model_validate(season)

    async def get_episode(self, episode_id: EpisodeId) -> EpisodeSchema:
        episode = await self.db.get(Episode, episode_id)
        if not episode:
            msg = f"Episode {episode_id} not found"
            raise NotFoundError(msg)
        return EpisodeSchema.model_validate(episode)

    async def get_season_by_episode(self, episode_id: EpisodeId) -> SeasonSchema:
        stmt = (
            select(Season)
            .join(Season.episodes)
            .where(Episode.id == episode_id)
            .options(selectinload(Season.episodes))
        )
        season = (await self.db.execute(stmt)).unique().scalar_one_or_none()
        if not season:
            msg = f"Season for episode {episode_id} not found"
            raise NotFoundError(msg)
        return SeasonSchema.model_validate(season)

    async def get_season_by_number(
        self, season_number: int, show_id: ShowId
    ) -> SeasonSchema:
        stmt = (
            select(Season)
            .where(Season.show_id == show_id)
            .where(Season.number == season_number)
            .options(selectinload(Season.episodes), joinedload(Season.show))
        )
        result = (await self.db.execute(stmt)).unique().scalar_one_or_none()
        if not result:
            msg = f"Season {season_number} for show {show_id} not found"
            raise NotFoundError(msg)
        return SeasonSchema.model_validate(result)

    async def add_episode_file(
        self, episode_file: EpisodeFileSchema
    ) -> EpisodeFileSchema:
        return await self.add_media_file_base(
            file_schema=episode_file,
            model_class=EpisodeFile,
            schema_class=EpisodeFileSchema,
        )

    async def remove_episode_files_by_torrent_id(self, torrent_id: TorrentId) -> int:
        return await self.remove_files_by_torrent_id_base(
            torrent_id=torrent_id, model_class=EpisodeFile
        )

    async def get_episode_files_by_season_id(
        self, season_id: SeasonId
    ) -> list[EpisodeFileSchema]:
        stmt = select(EpisodeFile).join(Episode).where(Episode.season_id == season_id)
        results = (await self.db.execute(stmt)).scalars().all()
        return [EpisodeFileSchema.model_validate(ef) for ef in results]

    async def get_episode_files_by_episode_id(
        self, episode_id: EpisodeId
    ) -> list[EpisodeFileSchema]:
        stmt = select(EpisodeFile).where(EpisodeFile.episode_id == episode_id)
        results = (await self.db.execute(stmt)).scalars().all()
        return [EpisodeFileSchema.model_validate(sf) for sf in results]

    async def get_managed_episode_ids(self, show_id: ShowId) -> set[EpisodeId]:
        """Return episodes already imported or assigned to a download."""
        stmt = (
            select(EpisodeFile.episode_id)
            .distinct()
            .join(Episode, Episode.id == EpisodeFile.episode_id)
            .join(Season, Season.id == Episode.season_id)
            .where(Season.show_id == show_id)
        )
        results = (await self.db.execute(stmt)).scalars().all()
        return {EpisodeId(episode_id) for episode_id in results}

    async def get_episode_file_states(
        self, show_id: ShowId
    ) -> dict[EpisodeId, EpisodeFileState]:
        """Classify managed episodes as imported or still being downloaded.

        An episode file without a torrent was imported from disk (or its
        torrent record was removed after import), so it counts as present.
        """
        stmt = (
            select(
                EpisodeFile.episode_id, EpisodeFile.torrent_id, TorrentModel.imported
            )
            .join(Episode, Episode.id == EpisodeFile.episode_id)
            .join(Season, Season.id == Episode.season_id)
            .outerjoin(TorrentModel, TorrentModel.id == EpisodeFile.torrent_id)
            .where(Season.show_id == show_id)
        )
        states: dict[EpisodeId, EpisodeFileState] = {}
        for episode_id, torrent_id, imported in (await self.db.execute(stmt)).all():
            key = EpisodeId(episode_id)
            if torrent_id is None or imported:
                states[key] = EpisodeFileState.IN_LIBRARY
            else:
                states.setdefault(key, EpisodeFileState.DOWNLOADING)
        return states

    async def get_torrents_by_show_id(self, show_id: ShowId) -> list[TorrentSchema]:
        stmt = (
            select(TorrentModel)
            .distinct()
            .join(EpisodeFile, EpisodeFile.torrent_id == TorrentModel.id)
            .join(Episode, Episode.id == EpisodeFile.episode_id)
            .join(Season, Season.id == Episode.season_id)
            .where(Season.show_id == show_id)
        )
        results = (await self.db.execute(stmt)).scalars().unique().all()
        return [TorrentSchema.model_validate(t) for t in results]

    async def get_all_shows_with_torrents(self) -> list[ShowSchema]:
        stmt = (
            select(Show)
            .distinct()
            .join(Season, Show.id == Season.show_id)
            .join(Episode, Season.id == Episode.season_id)
            .join(EpisodeFile, Episode.id == EpisodeFile.episode_id)
            .join(TorrentModel, EpisodeFile.torrent_id == TorrentModel.id)
            .options(_load_show_tree())
            .order_by(Show.name)
        )
        results = (await self.db.execute(stmt)).scalars().unique().all()
        return [ShowSchema.model_validate(show) for show in results]

    async def get_seasons_by_torrent_id(
        self, torrent_id: TorrentId
    ) -> list[SeasonNumber]:
        stmt = (
            select(Season.number)
            .distinct()
            .join(Episode, Episode.season_id == Season.id)
            .join(EpisodeFile, EpisodeFile.episode_id == Episode.id)
            .where(EpisodeFile.torrent_id == torrent_id)
        )
        results = (await self.db.execute(stmt)).scalars().unique().all()
        return [SeasonNumber(x) for x in results]

    async def get_episodes_by_torrent_id(
        self, torrent_id: TorrentId
    ) -> list[EpisodeNumber]:
        stmt = (
            select(Episode.number)
            .distinct()
            .join(EpisodeFile, EpisodeFile.episode_id == Episode.id)
            .where(EpisodeFile.torrent_id == torrent_id)
            .order_by(Episode.number)
        )
        episode_numbers = (await self.db.execute(stmt)).scalars().all()
        return [EpisodeNumber(n) for n in episode_numbers]

    async def get_show_by_season_id(self, season_id: SeasonId) -> ShowSchema:
        stmt = (
            select(Show)
            .join(Season, Show.id == Season.show_id)
            .where(Season.id == season_id)
            .options(_load_show_tree())
        )
        result = (await self.db.execute(stmt)).unique().scalar_one_or_none()
        if not result:
            msg = f"Show for season {season_id} not found"
            raise NotFoundError(msg)
        return ShowSchema.model_validate(result)

    async def add_season_to_show(
        self, show_id: ShowId, season_data: SeasonSchema
    ) -> SeasonSchema:
        db_show = await self.db.get(Show, show_id)
        if not db_show:
            msg = f"Show {show_id} not found"
            raise NotFoundError(msg)
        stmt = (
            select(Season)
            .where(Season.show_id == show_id, Season.number == season_data.number)
            .options(selectinload(Season.episodes))
        )
        existing = (await self.db.execute(stmt)).unique().scalar_one_or_none()
        if existing:
            return SeasonSchema.model_validate(existing)
        db_season = Season(
            id=season_data.id,
            show_id=show_id,
            number=season_data.number,
            external_id=season_data.external_id,
            name=season_data.name,
            overview=season_data.overview,
            monitored=season_data.monitored,
            episodes=[
                Episode(
                    id=ep_schema.id,
                    number=ep_schema.number,
                    external_id=ep_schema.external_id,
                    title=ep_schema.title,
                    overview=ep_schema.overview,
                    air_date=ep_schema.air_date,
                )
                for ep_schema in season_data.episodes
            ],
        )
        self.db.add(db_season)
        try:
            await self.db.commit()
            await self.db.refresh(db_season, ["episodes"])
        except IntegrityError as e:
            await self.db.rollback()
            msg = f"Integrity error: {e.orig}"
            raise ConflictError(msg) from e
        except SQLAlchemyError:
            await self.db.rollback()
            raise
        return SeasonSchema.model_validate(db_season)

    async def add_episode_to_season(
        self, season_id: SeasonId, episode_data: EpisodeSchema
    ) -> EpisodeSchema:
        db_season = await self.db.get(Season, season_id)
        if not db_season:
            msg = f"Season {season_id} not found"
            raise NotFoundError(msg)
        stmt = select(Episode).where(
            Episode.season_id == season_id, Episode.number == episode_data.number
        )
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing:
            return EpisodeSchema.model_validate(existing)
        db_episode = Episode(
            id=episode_data.id,
            season_id=season_id,
            number=episode_data.number,
            external_id=episode_data.external_id,
            title=episode_data.title,
            overview=episode_data.overview,
            air_date=episode_data.air_date,
        )
        self.db.add(db_episode)
        try:
            await self.db.commit()
            await self.db.refresh(db_episode)
        except IntegrityError as e:
            await self.db.rollback()
            msg = f"Integrity error: {e.orig}"
            raise ConflictError(msg) from e
        except SQLAlchemyError:
            await self.db.rollback()
            raise
        return EpisodeSchema.model_validate(db_episode)

    async def update_show_attributes(
        self,
        show_id: ShowId,
        name: str | None = None,
        overview: str | None = None,
        year: int | None = None,
        ended: bool | None = None,
        continuous_download: bool | None = None,
        monitor_scope: MonitorScope | None = None,
        imdb_id: str | None = None,
    ) -> ShowSchema:
        db_show = await self.db.get(Show, show_id)
        if not db_show:
            msg = f"Show with id {show_id} not found."
            raise NotFoundError(msg)
        attributes = {
            "name": name,
            "overview": overview,
            "year": year,
            "ended": ended,
            "continuous_download": continuous_download,
            "monitor_scope": monitor_scope.value if monitor_scope is not None else None,
            "imdb_id": imdb_id,
        }
        updated = False
        for key, value in attributes.items():
            if value is not None and getattr(db_show, key) != value:
                setattr(db_show, key, value)
                updated = True
        if updated:
            try:
                await self.db.commit()
            except SQLAlchemyError:
                await self.db.rollback()
                raise

        # Always reload the relationship tree before schema validation. Calling
        # the generic update helper here triggers an async lazy load and raises
        # MissingGreenlet for shows that already have seasons.
        return await self.get_show_by_id(show_id)

    async def update_season_attributes(
        self,
        season_id: SeasonId,
        name: str | None = None,
        overview: str | None = None,
        monitored: bool | None = None,
    ) -> SeasonSchema:
        # selectinload episodes so SeasonSchema.model_validate doesn't trip
        # an implicit lazy load under AsyncSession.
        db_season = await self.db.get(
            Season, season_id, options=[selectinload(Season.episodes)]
        )
        if not db_season:
            msg = f"Season {season_id} not found"
            raise NotFoundError(msg)
        updated = False
        if name is not None and db_season.name != name:
            db_season.name = name
            updated = True
        if overview is not None and db_season.overview != overview:
            db_season.overview = overview
            updated = True
        if monitored is not None and db_season.monitored != monitored:
            db_season.monitored = monitored
            updated = True
        if updated:
            try:
                await self.db.commit()
                await self.db.refresh(db_season, ["episodes"])
            except SQLAlchemyError:
                await self.db.rollback()
                raise
        return SeasonSchema.model_validate(db_season)

    async def configure_show_monitoring(
        self,
        show_id: ShowId,
        *,
        monitored: bool,
        monitor_scope: MonitorScope,
        monitored_season_numbers: set[int] | None = None,
    ) -> ShowSchema:
        stmt = select(Show).where(Show.id == show_id).options(_load_show_tree())
        db_show = (await self.db.execute(stmt)).unique().scalar_one_or_none()
        if db_show is None:
            msg = f"Show with id {show_id} not found."
            raise NotFoundError(msg)

        selected = monitored_season_numbers or set()
        available = {season.number for season in db_show.seasons}
        unknown = selected - available
        if monitored and monitor_scope == MonitorScope.SPECIFIC and not selected:
            msg = "Select at least one season when monitoring specific seasons."
            raise ValueError(msg)
        if unknown:
            msg = f"Unknown season numbers: {', '.join(map(str, sorted(unknown)))}"
            raise ValueError(msg)

        db_show.continuous_download = monitored
        db_show.monitor_scope = monitor_scope.value
        for season in db_show.seasons:
            season.monitored = monitored and (
                monitor_scope == MonitorScope.ENTIRE or season.number in selected
            )
        try:
            await self.db.commit()
        except SQLAlchemyError:
            await self.db.rollback()
            raise
        return await self.get_show_by_id(show_id)

    async def update_episode_attributes(
        self,
        episode_id: EpisodeId,
        title: str | None = None,
        overview: str | None = None,
        air_date: date | None = None,
    ) -> EpisodeSchema:
        db_episode = await self.db.get(Episode, episode_id)
        if not db_episode:
            msg = f"Episode {episode_id} not found"
            raise NotFoundError(msg)
        updated = False
        if title is not None and db_episode.title != title:
            db_episode.title = title
            updated = True
        if overview is not None and db_episode.overview != overview:
            db_episode.overview = overview
            updated = True
        if air_date is not None and db_episode.air_date != air_date:
            db_episode.air_date = air_date
            updated = True
        if updated:
            try:
                await self.db.commit()
                await self.db.refresh(db_episode)
            except SQLAlchemyError:
                await self.db.rollback()
                raise
        return EpisodeSchema.model_validate(db_episode)
