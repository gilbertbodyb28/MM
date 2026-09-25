import asyncio
import logging
import shutil
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from media_manager.common.service import BaseMediaService
from media_manager.config import MediaManagerConfig
from media_manager.indexer.schemas import IndexerQueryResult, IndexerQueryResultId
from media_manager.indexer.service import IndexerService
from media_manager.indexer.utils import evaluate_indexer_query_results
from media_manager.movies.importer import MovieImportService
from media_manager.movies.metadata import MovieMetadataService
from media_manager.movies.repository import MovieRepository
from media_manager.movies.schemas import (
    Movie,
    MovieFile,
    MovieId,
    PublicMovie,
    PublicMovieFile,
    RichMovieTorrent,
)
from media_manager.notification.service import NotificationService
from media_manager.torrent.schemas import (
    Torrent,
)
from media_manager.torrent.service import TorrentService

log = logging.getLogger(__name__)


class MovieService(BaseMediaService[Movie, Movie]):
    def __init__(
        self,
        movie_repository: MovieRepository,
        torrent_service: TorrentService,
        indexer_service: IndexerService,
        notification_service: NotificationService,
        movie_import_service: MovieImportService,
        movie_metadata_service: MovieMetadataService,
    ) -> None:
        super().__init__(
            repository=movie_repository,
            torrent_service=torrent_service,
            indexer_service=indexer_service,
            notification_service=notification_service,
        )
        self.movie_repository = movie_repository
        self.movie_import_service = movie_import_service
        self.movie_metadata_service = movie_metadata_service

    async def delete_movie(
        self,
        movie: Movie,
        delete_files_on_disk: bool = False,
        delete_torrents: bool = False,
    ) -> None:
        """
        Delete a movie from the database, optionally deleting files and torrents.

        :param movie: The movie to delete.
        :param delete_files_on_disk: Whether to delete the movie's files from disk.
        :param delete_torrents: Whether to delete associated torrents from the torrent client.
        """
        if delete_files_on_disk or delete_torrents:
            if delete_files_on_disk:
                # Get the movie's directory path
                movie_dir = self.get_movie_root_path(movie=movie)

                if movie_dir.exists() and movie_dir.is_dir():
                    try:
                        await asyncio.to_thread(shutil.rmtree, movie_dir)
                        log.info(f"Deleted movie directory: {movie_dir}")
                    except OSError:
                        log.exception(f"Deleting movie directory: {movie_dir}")

            if delete_torrents:
                # Get all torrents associated with this movie
                movie_torrents = await self.movie_repository.get_torrents_by_movie_id(
                    movie_id=movie.id
                )

                for movie_torrent in movie_torrents:
                    torrent = await self.torrent_service.get_torrent_by_id(
                        torrent_id=movie_torrent.torrent_id
                    )
                    try:
                        await self.torrent_service.cancel_download(
                            torrent=torrent, delete_files=True
                        )
                        log.info(f"Deleted torrent: {torrent.torrent_title}")
                    except Exception:
                        log.exception(f"Failed to delete torrent {torrent.hash}")

        # Delete from database
        await self.movie_repository.delete_movie(movie.id)

    async def get_public_movie_files(self, movie: Movie) -> list[PublicMovieFile]:
        """
        Get all public movie files for a given movie.

        :param movie: The movie object.
        :return: A list of public movie files.
        """
        movie_files = await self.movie_repository.get_movie_files_by_movie_id(
            movie_id=movie.id
        )
        public_movie_files = [PublicMovieFile.model_validate(x) for x in movie_files]
        result = []
        for movie_file in public_movie_files:
            movie_file.imported = await self.movie_file_exists_on_file(movie_file=movie_file)
            result.append(movie_file)
        return result

    async def get_all_available_torrents_for_movie(
        self, movie: Movie, search_query_override: str | None = None
    ) -> list[IndexerQueryResult]:
        """
        Get all available torrents for a given movie.

        :param movie: The movie object.
        :param search_query_override: Optional override for the search query.
        :return: A list of indexer query results.
        """
        if search_query_override:
            return await self.indexer_service.search(query=search_query_override, is_tv=False)

        torrents = await self.indexer_service.search_movie(movie=movie)

        return evaluate_indexer_query_results(
            is_tv=False, query_results=torrents, media=movie
        )

    async def get_public_movie_by_id(self, movie: Movie) -> PublicMovie:
        """
        Get a public movie from a Movie object.

        :param movie: The movie object.
        :return: A public movie.
        """
        torrents = (await self.get_torrents_for_movie(movie=movie)).torrents
        public_movie = PublicMovie.model_validate(movie)
        public_movie.downloaded = await self.is_movie_downloaded(movie=movie)
        public_movie.torrents = torrents
        return public_movie

    async def get_movie_by_id(self, movie_id: MovieId) -> Movie:
        """
        Get a movie by its ID.

        :param movie_id: The ID of the movie.
        :return: The movie.
        """
        return await self.movie_repository.get_movie_by_id(movie_id)

    async def is_movie_downloaded(self, movie: Movie) -> bool:
        """
        Check if a movie is downloaded.

        :param movie: The movie object.
        :return: True if the movie is downloaded, False otherwise.
        """
        movie_files = await self.movie_repository.get_movie_files_by_movie_id(
            movie_id=movie.id
        )
        for movie_file in movie_files:
            if await self.movie_file_exists_on_file(movie_file=movie_file):
                return True
        return False

    async def movie_file_exists_on_file(self, movie_file: MovieFile) -> bool:
        """
        Check if a movie file exists on the filesystem.

        :param movie_file: The movie file to check.
        :return: True if the file exists, False otherwise.
        """
        if movie_file.torrent_id is None:
            return True
        torrent_file = await self.torrent_service.get_torrent_by_id(
            torrent_id=movie_file.torrent_id
        )
        return bool(torrent_file.imported)

    async def get_movie_by_external_id(
        self, external_id: int, metadata_provider: str
    ) -> Movie | None:
        """
        Get a movie by its external ID and metadata provider.

        :param external_id: The external ID of the movie.
        :param metadata_provider: The metadata provider.
        :return: The movie or None if not found.
        """
        return await self.movie_repository.get_movie_by_external_id(
            external_id=external_id, metadata_provider=metadata_provider
        )

    async def set_movie_library(self, movie: Movie, library: str) -> None:
        await self.movie_repository.set_movie_library(movie.id, library)

    async def get_all_movies(self) -> list[Movie]:
        """
        Get all movies in the library.
        """
        return await self.get_all_media()

    async def get_torrents_for_movie(self, movie: Movie) -> RichMovieTorrent:
        """
        Get torrents for a given movie.

        :param movie: The movie.
        :return: A rich movie torrent.
        """
        movie_torrents = await self.movie_repository.get_torrents_by_movie_id(
            movie_id=movie.id
        )
        return RichMovieTorrent(
            movie_id=movie.id,
            name=movie.name,
            year=movie.year,
            metadata_provider=movie.metadata_provider,
            torrents=movie_torrents,
        )

    async def get_all_movies_with_torrents(self) -> list[RichMovieTorrent]:
        """
        Get all movies with torrents.

        :return: A list of rich movie torrents.
        """
        movies = await self.movie_repository.get_all_movies_with_torrents()
        return [await self.get_torrents_for_movie(movie=movie) for movie in movies]

    async def download_torrent(
        self,
        public_indexer_result_id: IndexerQueryResultId,
        movie: Movie,
        override_movie_file_path_suffix: str = "",
    ) -> Torrent:
        """
        Download a torrent for a given indexer result and movie.

        :param public_indexer_result_id: The ID of the indexer result.
        :param movie: The movie object.
        :param override_movie_file_path_suffix: Optional override for the file path suffix.
        :return: The downloaded torrent.
        """
        indexer_result = await self.indexer_service.get_result(
            result_id=public_indexer_result_id
        )
        movie_torrent = await self.torrent_service.download(indexer_result=indexer_result)
        await self.torrent_service.pause_download(torrent=movie_torrent)
        movie_file = MovieFile(
            movie_id=movie.id,
            quality=indexer_result.quality,
            torrent_id=movie_torrent.id,
            file_path_suffix=override_movie_file_path_suffix,
        )
        try:
            await self.movie_repository.add_movie_file(movie_file=movie_file)
        except IntegrityError:
            log.warning(
                f"Movie file for movie {movie.name} and torrent {movie_torrent.title} already exists"
            )
            await self.torrent_service.cancel_download(
                torrent=movie_torrent, delete_files=True
            )
            raise
        else:
            log.info(
                f"Added movie file for movie {movie.name} and torrent {movie_torrent.title}"
            )
            await self.torrent_service.resume_download(torrent=movie_torrent)
        return movie_torrent

    def get_movie_root_path(self, movie: Movie) -> Path:
        misc_config = MediaManagerConfig().misc
        return self.get_root_directory(
            media=movie,
            default_dir=misc_config.movie_directory,
            libraries=misc_config.movie_libraries,
        )

    async def import_all_torrents(self) -> None:
        """
        Delegate to MovieImportService.
        """
        await self.movie_import_service.import_all_torrents()

    async def update_all_metadata(self) -> None:
        """
        Delegate to MovieMetadataService.
        """
        await self.movie_metadata_service.update_all_metadata()
