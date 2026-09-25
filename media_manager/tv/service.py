import asyncio
import re
import shutil
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from media_manager.common.service import BaseMediaService
from media_manager.config import MediaManagerConfig
from media_manager.exceptions import ConflictError, NotFoundError
from media_manager.indexer.schemas import IndexerQueryResult, IndexerQueryResultId
from media_manager.indexer.service import IndexerService
from media_manager.indexer.utils import evaluate_indexer_query_results
from media_manager.notification.service import NotificationService
from media_manager.torrent.schemas import (
    Torrent,
)
from media_manager.torrent.service import TorrentService
from media_manager.tv import log
from media_manager.tv.importer import TvImportService
from media_manager.tv.metadata import TvMetadataService
from media_manager.tv.repository import TvRepository
from media_manager.tv.schemas import (
    Episode,
    EpisodeFile,
    EpisodeId,
    EpisodeNumber,
    MonitorScope,
    PublicEpisode,
    PublicEpisodeFile,
    PublicSeason,
    PublicShow,
    RichSeasonTorrent,
    RichShowTorrent,
    Season,
    SeasonId,
    Show,
    ShowId,
)


class TvService(BaseMediaService[Show, Show]):
    def __init__(
        self,
        tv_repository: TvRepository,
        torrent_service: TorrentService,
        indexer_service: IndexerService,
        notification_service: NotificationService,
        tv_import_service: TvImportService,
        tv_metadata_service: TvMetadataService,
    ) -> None:
        super().__init__(
            repository=tv_repository,
            torrent_service=torrent_service,
            indexer_service=indexer_service,
            notification_service=notification_service,
        )
        self.tv_repository = tv_repository
        self.tv_import_service = tv_import_service
        self.tv_metadata_service = tv_metadata_service

    async def get_total_downloaded_episodes_count(self) -> int:
        """
        Get total number of downloaded episodes.
        """

        return await self.tv_repository.get_total_downloaded_episodes_count()

    async def set_show_library(self, show: Show, library: str) -> None:
        await self.tv_repository.set_show_library(show.id, library)

    async def get_all_shows(self) -> list[Show]:
        """
        Get all shows in the library.
        """
        # Use the TV-specific eager-loaded query so ShowSchema validation
        # doesn't trigger lazy loads on seasons/episodes under AsyncSession.
        return await self.tv_repository.get_shows()

    async def delete_show(
        self,
        show: Show,
        delete_files_on_disk: bool = False,
        delete_torrents: bool = False,
    ) -> None:
        """
        Delete a show from the database, optionally deleting files and torrents.

        :param show: The show to delete.
        :param delete_files_on_disk: Whether to delete the show's files from disk.
        :param delete_torrents: Whether to delete associated torrents from the torrent client.
        """
        if delete_files_on_disk or delete_torrents:
            log.debug(f"Deleting ID: {show.id} - Name: {show.name}")

            if delete_files_on_disk:
                show_dir = self.get_root_show_directory(show=show)

                log.debug(f"Attempt to delete show directory: {show_dir}")
                if show_dir.exists() and show_dir.is_dir():
                    await asyncio.to_thread(shutil.rmtree, show_dir)
                    log.info(f"Deleted show directory: {show_dir}")

            if delete_torrents:
                torrents = await self.tv_repository.get_torrents_by_show_id(
                    show_id=show.id
                )
                for torrent in torrents:
                    try:
                        await self.torrent_service.cancel_download(
                            torrent, delete_files=True
                        )
                        await self.torrent_service.delete_torrent(torrent_id=torrent.id)
                        log.info(f"Deleted torrent: {torrent.hash}")
                    except Exception:
                        log.warning(
                            f"Failed to delete torrent {torrent.hash}", exc_info=True
                        )

        await self.tv_repository.delete_show(show.id)

    async def get_public_episode_files_by_season_id(
        self, season: Season
    ) -> list[PublicEpisodeFile]:
        """
        Get all public episode files for a given season.

        :param season: The season object.
        :return: A list of public episode files.
        """
        episode_files = await self.tv_repository.get_episode_files_by_season_id(
            season_id=season.id
        )
        public_episode_files = [
            PublicEpisodeFile.model_validate(x) for x in episode_files
        ]
        result = []
        for episode_file in public_episode_files:
            if await self.episode_file_exists_on_file(episode_file=episode_file):
                episode_file.downloaded = True
            result.append(episode_file)
        return result

    async def get_all_available_torrents_for_a_season(
        self,
        season_number: int,
        show_id: ShowId,
        search_query_override: str | None = None,
    ) -> list[IndexerQueryResult]:
        """
        Get all available torrents for a given season.

        :param season_number: The number of the season.
        :param show_id: The ID of the show.
        :param search_query_override: Optional override for the search query.
        :return: A list of indexer query results.
        """

        if search_query_override:
            return await self.indexer_service.search(
                query=search_query_override, is_tv=True
            )

        show = await self.tv_repository.get_show_by_id(show_id=show_id)

        torrents = await self.indexer_service.search_season(
            show=show, season_number=season_number
        )

        results = [torrent for torrent in torrents if season_number in torrent.season]

        return evaluate_indexer_query_results(
            is_tv=True, query_results=results, media=show
        )

    async def get_episode_releases(
        self,
        *,
        show: Show,
        episode_id: EpisodeId,
    ) -> list[IndexerQueryResult]:
        """Search and rank releases for one exact episode.

        The episode route deliberately does not fall back to season packs. A
        row-level action must never attach a different episode (or an entire
        season) to the selected row.
        """
        season, episode = self._get_episode_context(show, episode_id)
        results = await self.indexer_service.search_episode(
            show=show,
            season_number=int(season.number),
            episode_number=int(episode.number),
        )
        matching = [
            result
            for result in results
            if self._release_matches_episode(
                result=result,
                show=show,
                season_number=int(season.number),
                episode_number=int(episode.number),
            )
        ]
        ranked = evaluate_indexer_query_results(
            query_results=matching,
            media=show,
            is_tv=True,
        )

        unique: list[IndexerQueryResult] = []
        seen: set[tuple[str, int, bool]] = set()
        for result in ranked:
            key = (result.title.casefold().strip(), result.size, result.usenet)
            if key in seen:
                continue
            seen.add(key)
            unique.append(result)
        return unique

    async def download_episode_release(
        self,
        *,
        show: Show,
        episode_id: EpisodeId,
        result_id: IndexerQueryResultId,
    ) -> Torrent:
        """Validate and submit one interactive-search result for one episode."""
        season, episode = self._get_episode_context(show, episode_id)
        managed = await self.tv_repository.get_managed_episode_ids(show.id)
        if episode_id in managed:
            msg = f"Episode S{season.number:02d}E{episode.number:02d} is already managed."
            raise ConflictError(msg)

        result = await self.indexer_service.get_result(result_id=result_id)
        if not self._release_matches_episode(
            result=result,
            show=show,
            season_number=int(season.number),
            episode_number=int(episode.number),
        ):
            msg = (
                f"Release {result.title} does not match {show.name} "
                f"S{season.number:02d}E{episode.number:02d}."
            )
            raise ConflictError(msg)

        return await self.download_torrent(
            public_indexer_result_id=result.id,
            show_id=show.id,
            episode_ids={episode_id},
        )

    @staticmethod
    def _get_episode_context(
        show: Show,
        episode_id: EpisodeId,
    ) -> tuple[Season, Episode]:
        for season in show.seasons:
            for episode in season.episodes:
                if episode.id == episode_id:
                    return season, episode
        msg = f"Episode {episode_id} does not belong to show {show.id}."
        raise NotFoundError(msg)

    @staticmethod
    def _release_matches_episode(
        *,
        result: IndexerQueryResult,
        show: Show,
        season_number: int,
        episode_number: int,
    ) -> bool:
        normalized_show = re.sub(r"[^a-z0-9]+", "", show.name.casefold())
        normalized_release = re.sub(r"[^a-z0-9]+", "", result.title.casefold())
        return (
            bool(normalized_show)
            and normalized_show in normalized_release
            and season_number in result.season
            and result.episode == [episode_number]
        )

    async def get_public_show_by_id(self, show: Show) -> PublicShow:
        """
        Get a public show from a Show object.

        :param show: The show object.
        :return: A public show.
        """
        public_show = PublicShow.model_validate(show)
        public_seasons: list[PublicSeason] = []

        for season in show.seasons:
            public_season = PublicSeason.model_validate(season)

            for episode in public_season.episodes:
                episode.downloaded = await self.is_episode_downloaded(
                    episode=episode,
                    season=season,
                    show=show,
                )

            # A season is considered downloaded if it has episodes and all of them are downloaded,
            # matching the behavior of is_season_downloaded.
            public_season.downloaded = bool(public_season.episodes) and all(
                episode.downloaded for episode in public_season.episodes
            )
            public_seasons.append(public_season)

        public_show.seasons = public_seasons
        return public_show

    async def get_show_by_id(self, show_id: ShowId) -> Show:
        """
        Get a show by its ID.

        :param show_id: The ID of the show.
        :return: The show.
        """
        return await self.tv_repository.get_show_by_id(show_id=show_id)

    async def is_season_downloaded(self, season: Season, show: Show) -> bool:
        """
        Check if a season is downloaded.

        :param season: The season object.
        :param show: The show object.
        :return: True if the season is downloaded, False otherwise.
        """
        episodes = season.episodes

        if not episodes:
            return False

        for episode in episodes:
            if not await self.is_episode_downloaded(
                episode=episode, season=season, show=show
            ):
                return False
        return True

    async def is_episode_downloaded(
        self, episode: Episode | PublicEpisode, season: Season, show: Show
    ) -> bool:
        """
        Check if an episode is downloaded and imported (file exists on disk).

        An episode is considered downloaded if:
        - There is at least one EpisodeFile in the database AND
        - A matching episode file exists in the season directory on disk.

        :param episode: The episode object.
        :param season: The season object.
        :param show: The show object.
        :return: True if the episode is downloaded and imported, False otherwise.
        """
        episode_files = await self.tv_repository.get_episode_files_by_episode_id(
            episode_id=episode.id
        )

        if not episode_files:
            return False

        season_dir = self.get_root_season_directory(show, season.number)

        if not season_dir.exists():
            return False

        episode_token = f"S{season.number:02d}E{episode.number:02d}"

        video_extensions = {".mkv", ".mp4", ".avi", ".mov"}

        try:
            for file in season_dir.iterdir():
                if (
                    file.is_file()
                    and episode_token.lower() in file.name.lower()
                    and file.suffix.lower() in video_extensions
                ):
                    return True

        except OSError as e:
            log.error(
                f"Disk check failed for episode {episode.id} in {season_dir}: {e}"
            )

        return False

    async def episode_file_exists_on_file(self, episode_file: EpisodeFile) -> bool:
        """
        Check if an episode file exists on the filesystem.

        :param episode_file: The episode file to check.
        :return: True if the file exists, False otherwise.
        """
        if episode_file.torrent_id is None:
            return True
        try:
            torrent_file = await self.torrent_service.get_torrent_by_id(
                torrent_id=episode_file.torrent_id
            )

            if torrent_file.imported:
                return True
        except RuntimeError:
            log.exception("Error retrieving torrent")

        return False

    async def get_show_by_external_id(
        self, external_id: int, metadata_provider: str
    ) -> Show | None:
        """
        Get a show by its external ID and metadata provider.

        :param external_id: The external ID of the show.
        :param metadata_provider: The metadata provider.
        :return: The show or None if not found.
        """
        return await self.tv_repository.get_show_by_external_id(
            external_id=external_id, metadata_provider=metadata_provider
        )

    async def get_season(self, season_id: SeasonId) -> Season:
        """
        Get a season by its ID.

        :param season_id: The ID of the season.
        :return: The season.
        """
        return await self.tv_repository.get_season(season_id=season_id)

    async def get_episode(self, episode_id: EpisodeId) -> Episode:
        """
        Get an episode by its ID.

        :param episode_id: The ID of the episode.
        :return: The episode.
        """
        return await self.tv_repository.get_episode(episode_id=episode_id)

    async def get_season_by_episode(self, episode_id: EpisodeId) -> Season:
        """
        Get a season by the episode ID.

        :param episode_id: The ID of the episode.
        :return: The season.
        """
        return await self.tv_repository.get_season_by_episode(episode_id=episode_id)

    async def get_torrents_for_show(self, show: Show) -> RichShowTorrent:
        """
        Get torrents for a given show.

        :param show: The show.
        :return: A rich show torrent.
        """
        show_torrents = await self.tv_repository.get_torrents_by_show_id(
            show_id=show.id
        )
        rich_season_torrents = []
        for show_torrent in show_torrents:
            seasons = await self.tv_repository.get_seasons_by_torrent_id(
                torrent_id=show_torrent.id
            )
            episodes = await self.tv_repository.get_episodes_by_torrent_id(
                torrent_id=show_torrent.id
            )
            episode_files = await self.torrent_service.get_episode_files_of_torrent(
                torrent=show_torrent
            )

            file_path_suffix = (
                episode_files[0].file_path_suffix if episode_files else ""
            )
            season_torrent = RichSeasonTorrent(
                torrent_id=show_torrent.id,
                torrent_title=show_torrent.title,
                status=show_torrent.status,
                quality=show_torrent.quality,
                imported=show_torrent.imported,
                seasons=seasons,
                episodes=episodes if len(seasons) == 1 else [],
                file_path_suffix=file_path_suffix,
                usenet=show_torrent.usenet,
            )
            rich_season_torrents.append(season_torrent)

        return RichShowTorrent(
            show_id=show.id,
            name=show.name,
            year=show.year,
            metadata_provider=show.metadata_provider,
            torrents=rich_season_torrents,
        )

    async def get_all_shows_with_torrents(self) -> list[RichShowTorrent]:
        """
        Get all shows with torrents.

        :return: A list of rich show torrents.
        """
        shows = await self.tv_repository.get_all_shows_with_torrents()
        return [await self.get_torrents_for_show(show=show) for show in shows]

    async def download_torrent(
        self,
        public_indexer_result_id: IndexerQueryResultId,
        show_id: ShowId,
        override_show_file_path_suffix: str = "",
        episode_ids: set[EpisodeId] | None = None,
    ) -> Torrent:
        """
        Download a torrent for a given indexer result and show.

        :param public_indexer_result_id: The ID of the indexer result.
        :param show_id: The ID of the show.
        :param override_show_file_path_suffix: Optional override for the file path suffix.
        :param episode_ids: Optional exact episode targets for automatic downloads.
        :return: The downloaded torrent.
        """
        indexer_result = await self.indexer_service.get_result(
            result_id=public_indexer_result_id
        )

        episode_ids_to_add: list[EpisodeId] = []
        for season_number in indexer_result.season:
            try:
                season = await self.tv_repository.get_season_by_number(
                    season_number=season_number, show_id=show_id
                )
            except NotFoundError:
                log.warning(
                    "Indexer result %s contains unknown season %s for show %s",
                    indexer_result.title,
                    season_number,
                    show_id,
                )
                continue

            episodes = {episode.number: episode.id for episode in season.episodes}

            if indexer_result.episode:
                release_episode_ids = []
                missing_episodes = []
                for ep_number in indexer_result.episode:
                    ep_id = episodes.get(EpisodeNumber(ep_number))
                    if ep_id is None:
                        missing_episodes.append(ep_number)
                        continue
                    release_episode_ids.append(ep_id)
                if missing_episodes:
                    log.warning(
                        "Some episodes from indexer result were not found in season %s "
                        "for show %s and will be skipped: %s",
                        season.id,
                        show_id,
                        ", ".join(str(ep) for ep in missing_episodes),
                    )
            else:
                release_episode_ids = [episode.id for episode in season.episodes]

            if episode_ids is not None:
                release_episode_ids = [
                    episode_id
                    for episode_id in release_episode_ids
                    if episode_id in episode_ids
                ]
            episode_ids_to_add.extend(release_episode_ids)

        # A multi-episode title can mention the same episode more than once.
        episode_ids_to_add = list(dict.fromkeys(episode_ids_to_add))

        if episode_ids is not None:
            managed_episode_ids = await self.tv_repository.get_managed_episode_ids(
                show_id=show_id
            )
            episode_ids_to_add = [
                episode_id
                for episode_id in episode_ids_to_add
                if episode_id not in managed_episode_ids
            ]

        if not episode_ids_to_add:
            msg = (
                f"Release {indexer_result.title} has no unmanaged matching episodes "
                f"for show {show_id}."
            )
            raise ConflictError(msg)

        show_torrent = await self.torrent_service.download(
            indexer_result=indexer_result
        )
        await self.torrent_service.pause_download(torrent=show_torrent)

        try:
            for episode_id in episode_ids_to_add:
                episode_file = EpisodeFile(
                    episode_id=episode_id,
                    quality=indexer_result.quality,
                    torrent_id=show_torrent.id,
                    file_path_suffix=override_show_file_path_suffix,
                )
                await self.tv_repository.add_episode_file(episode_file=episode_file)

        except IntegrityError:
            log.error(
                "An episode file for automatic release %s already exists; "
                "rolling back its associations.",
                indexer_result.title,
            )
            await self.tv_repository.remove_episode_files_by_torrent_id(show_torrent.id)
            await self.torrent_service.cancel_download(
                torrent=show_torrent, delete_files=True
            )
            raise
        else:
            log.info(
                f"Successfully added episode files for torrent {show_torrent.title} and show ID {show_id}"
            )
            await self.torrent_service.resume_download(torrent=show_torrent)

        return show_torrent

    def get_root_show_directory(self, show: Show) -> Path:
        misc_config = MediaManagerConfig().misc
        return self.get_root_directory(
            media=show,
            default_dir=misc_config.tv_directory,
            libraries=misc_config.tv_libraries,
        )

    def get_root_season_directory(self, show: Show, season_number: int) -> Path:
        return self.get_root_show_directory(show) / Path(f"Season {season_number}")

    async def set_show_continuous_download(
        self, show: Show, continuous_download: bool
    ) -> Show:
        """
        Set the continuous download flag for a show.

        :param show: The show object.
        :param continuous_download: True to enable continuous download, False to disable.
        :return: The updated Show object.
        """
        return await self.tv_repository.configure_show_monitoring(
            show_id=show.id,
            monitored=continuous_download,
            monitor_scope=MonitorScope.ENTIRE,
        )

    async def configure_show_monitoring(
        self,
        show: Show,
        *,
        monitored: bool,
        monitor_scope: MonitorScope,
        monitored_season_numbers: set[int] | None = None,
    ) -> Show:
        return await self.tv_repository.configure_show_monitoring(
            show_id=show.id,
            monitored=monitored,
            monitor_scope=monitor_scope,
            monitored_season_numbers=monitored_season_numbers,
        )

    async def import_all_torrents(self) -> None:
        """
        Delegate to TvImportService.
        """
        await self.tv_import_service.import_all_torrents()

    async def update_all_non_ended_shows_metadata(self) -> None:
        """
        Delegate to TvMetadataService.
        """
        await self.tv_metadata_service.update_all_non_ended_shows_metadata()
