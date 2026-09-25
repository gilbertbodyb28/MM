import asyncio
import logging

from media_manager.config import MediaManagerConfig
from media_manager.indexer.indexers.generic import GenericIndexer
from media_manager.indexer.indexers.jackett import Jackett
from media_manager.indexer.indexers.prowlarr import Prowlarr
from media_manager.indexer.repository import IndexerRepository
from media_manager.indexer.schemas import IndexerQueryResult, IndexerQueryResultId
from media_manager.movies.schemas import Movie
from media_manager.torrent.utils import remove_special_chars_and_parentheses
from media_manager.tv.schemas import Show

log = logging.getLogger(__name__)


class IndexerService:
    def __init__(self, indexer_repository: IndexerRepository) -> None:
        config = MediaManagerConfig()
        self.repository = indexer_repository
        self.indexers: list[GenericIndexer] = []

        if config.indexers.prowlarr.enabled:
            self.indexers.append(Prowlarr())
        if config.indexers.jackett.enabled:
            self.indexers.append(Jackett())

    async def get_result(self, result_id: IndexerQueryResultId) -> IndexerQueryResult:
        return await self.repository.get_result(result_id=result_id)

    async def search(self, query: str, is_tv: bool) -> list[IndexerQueryResult]:
        """
        Search for results using the indexers based on a query.

        :param is_tv: Whether the search is for TV shows or movies.
        :param query: The search query, is used as a fallback in case indexers don't support e.g. TMDB ID based search.
        :return: A list of search results.
        """
        log.debug(f"Searching for: {query}")
        results: list[IndexerQueryResult] = []

        for indexer in self.indexers:
            try:
                indexer_results = await asyncio.to_thread(
                    indexer.search, query, is_tv=is_tv
                )
                results.extend(self._bounded_results(indexer, indexer_results))
                log.debug(
                    f"Indexer {indexer.__class__.__name__} returned {len(indexer_results)} results for query: {query}"
                )
            except Exception:
                log.exception(
                    f"Indexer {indexer.__class__.__name__} failed for query '{query}'"
                )

        return await self._deduplicate_and_save(results)

    async def search_movie(self, movie: Movie) -> list[IndexerQueryResult]:
        query = f"{movie.name} {movie.year}"
        query = remove_special_chars_and_parentheses(query)

        results: list[IndexerQueryResult] = []
        for indexer in self.indexers:
            try:
                indexer_results = await asyncio.to_thread(
                    indexer.search_movie, query=query, movie=movie
                )
                if indexer_results:
                    results.extend(self._bounded_results(indexer, indexer_results))
            except Exception:
                log.exception(
                    f"Indexer {indexer.__class__.__name__} failed for movie search '{query}'"
                )

        return await self._deduplicate_and_save(results)

    async def search_season(
        self, show: Show, season_number: int
    ) -> list[IndexerQueryResult]:
        query = f"{show.name} {show.year} S{season_number:02d}"
        query = remove_special_chars_and_parentheses(query)

        results: list[IndexerQueryResult] = []
        for indexer in self.indexers:
            try:
                indexer_results = await asyncio.to_thread(
                    indexer.search_season,
                    query=query,
                    show=show,
                    season_number=season_number,
                )
                if indexer_results:
                    results.extend(self._bounded_results(indexer, indexer_results))
            except Exception:
                log.exception(
                    f"Indexer {indexer.__class__.__name__} failed for season search '{query}'"
                )

        return await self._deduplicate_and_save(results)

    async def search_episode(
        self,
        show: Show,
        season_number: int,
        episode_number: int,
    ) -> list[IndexerQueryResult]:
        query = (
            f"{show.name} {show.year or ''} S{season_number:02d}E{episode_number:02d}"
        )
        query = remove_special_chars_and_parentheses(query)

        results: list[IndexerQueryResult] = []
        for indexer in self.indexers:
            try:
                indexer_results = await asyncio.to_thread(
                    indexer.search_episode,
                    query=query,
                    show=show,
                    season_number=season_number,
                    episode_number=episode_number,
                )
                if indexer_results:
                    results.extend(self._bounded_results(indexer, indexer_results))
            except Exception:
                log.exception(
                    "Indexer %s failed for episode search '%s'",
                    indexer.__class__.__name__,
                    query,
                )

        return await self._deduplicate_and_save(results)

    @staticmethod
    def _bounded_results(
        indexer: GenericIndexer,
        results: list[IndexerQueryResult],
    ) -> list[IndexerQueryResult]:
        """Apply a defensive per-indexer cap even if an adapter ignores it."""
        configured_limit = getattr(indexer, "max_results", 1000)
        limit = max(1, min(int(configured_limit), 1000))
        if len(results) > limit:
            log.warning(
                "Indexer %s returned %s results; keeping the configured maximum of %s",
                indexer.__class__.__name__,
                len(results),
                limit,
            )
        return results[:limit]

    async def _deduplicate_and_save(
        self,
        results: list[IndexerQueryResult],
    ) -> list[IndexerQueryResult]:
        unique_results: list[IndexerQueryResult] = []
        seen_releases: set[tuple[str, int, bool]] = set()
        for result in results:
            release_key = (
                result.title.casefold().strip(),
                result.size,
                result.usenet,
            )
            if release_key in seen_releases:
                continue
            seen_releases.add(release_key)
            unique_results.append(result)

        if len(unique_results) != len(results):
            log.debug(
                "Removed %s duplicate indexer result(s) before persistence",
                len(results) - len(unique_results),
            )
        await self.repository.save_results(unique_results)
        return unique_results
