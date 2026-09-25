from abc import ABC, abstractmethod

from media_manager.indexer.schemas import IndexerQueryResult
from media_manager.movies.schemas import Movie
from media_manager.tv.schemas import Show


def describe_indexer_failure(source: str, error: BaseException) -> str:
    """Summarise a failed upstream request without its (secret-bearing) URL."""
    status_code = getattr(getattr(error, "response", None), "status_code", None)
    status = f" (HTTP {status_code})" if status_code else ""
    return f"{source}: {type(error).__name__}{status}"


class GenericIndexer(ABC):
    name: str

    def __init__(self, name: str) -> None:
        self.name = name

    def record_tolerated_failure(self, failure: str) -> None:
        """Remember an upstream source that failed while the others answered.

        Callers that report problems (such as the episode scanner) read and
        clear these with ``pop_tolerated_failures``.
        """
        failures: list[str] | None = getattr(self, "_tolerated_failures", None)
        if failures is None:
            failures = []
            self._tolerated_failures = failures
        failures.append(failure)

    def pop_tolerated_failures(self) -> list[str]:
        failures: list[str] = getattr(self, "_tolerated_failures", None) or []
        self._tolerated_failures = []
        return failures

    @abstractmethod
    def search(self, query: str, is_tv: bool) -> list[IndexerQueryResult]:
        """
        Sends a search request to the Indexer and returns the results.

        :param query: A string representing the search query.
        :param is_tv: A boolean indicating whether the search is for TV shows (True) or movies (False).
        :return: A list of IndexerQueryResult objects representing the search results.
        """
        raise NotImplementedError()

    @abstractmethod
    def search_season(
        self, query: str, show: Show, season_number: int
    ) -> list[IndexerQueryResult]:
        """
        Sends a search request to the Indexer for a specific season and returns the results.

        :param query: A string representing the search query, used as a fallback for indexers that don't support TMDB/IMDB ID-based search.
        :param show: The show to search for.
        :param season_number: The season number to search for.
        :return: A list of IndexerQueryResult objects representing the search results.
        """
        raise NotImplementedError()

    @abstractmethod
    def search_episode(
        self,
        query: str,
        show: Show,
        season_number: int,
        episode_number: int,
    ) -> list[IndexerQueryResult]:
        """Search for one episode, using media IDs when supported."""
        raise NotImplementedError()

    @abstractmethod
    def search_movie(self, query: str, movie: Movie) -> list[IndexerQueryResult]:
        """
        Sends a search request to the Indexer for a specific movie and returns the results.

        :param movie: The movie to search for.
        :param query: A string representing the search query, used as a fallback for indexers that don't support TMDB/IMDB ID-based search.
        :return: A list of IndexerQueryResult objects representing the search results.
        """
        raise NotImplementedError()
