import logging
from dataclasses import dataclass

from requests import Response, Session

from media_manager.config import MediaManagerConfig
from media_manager.indexer.indexers.generic import (
    GenericIndexer,
    describe_indexer_failure,
)
from media_manager.indexer.indexers.torznab_mixin import TorznabMixin
from media_manager.indexer.schemas import IndexerQueryResult
from media_manager.movies.schemas import Movie
from media_manager.tv.schemas import Show

log = logging.getLogger(__name__)


@dataclass
class IndexerInfo:
    id: int
    name: str

    supports_tv_search: bool
    supports_tv_search_tmdb: bool
    supports_tv_search_imdb: bool
    supports_tv_search_tvdb: bool
    supports_tv_search_season: bool
    supports_tv_search_episode: bool

    supports_movie_search: bool
    supports_movie_search_tmdb: bool
    supports_movie_search_imdb: bool
    supports_movie_search_tvdb: bool


class Prowlarr(GenericIndexer, TorznabMixin):
    def __init__(self) -> None:
        """
        A subclass of GenericIndexer for interacting with the Prowlarr API.
        """
        super().__init__(name="prowlarr")
        self.config = MediaManagerConfig().indexers.prowlarr
        self.max_results = self.config.max_results

    def _call_prowlarr_api(
        self,
        path: str,
        parameters: dict[str, str | int | None] | None = None,
    ) -> Response:
        url = f"{self.config.url}/api/v1{path}"
        headers = {"X-Api-Key": self.config.api_key}
        with Session() as session:
            response = session.get(
                url=url,
                params=parameters,
                timeout=self.config.timeout_seconds,
                headers=headers,
            )
            response.raise_for_status()
            return response

    def _newznab_search(
        self,
        indexer: IndexerInfo,
        parameters: dict[str, str | int | None] | None = None,
    ) -> list[IndexerQueryResult]:
        search_parameters = dict(parameters or {})
        search_parameters["limit"] = self.config.max_results
        response = self._call_prowlarr_api(
            path=f"/indexer/{indexer.id}/newznab", parameters=search_parameters
        )
        results = self.process_search_result(xml=response.content)[
            : self.config.max_results
        ]
        log.info(
            "Indexer %s returned %s results for search: %s",
            indexer.name,
            len(results),
            search_parameters,
        )
        return results

    def _get_indexers(self) -> list[IndexerInfo]:
        indexers = self._call_prowlarr_api(path="/indexer")
        indexers = indexers.json()
        indexer_info_list: list[IndexerInfo] = []
        for indexer in indexers:
            supports_tv_search = False
            supports_movie_search = False
            tv_search_params = []
            movie_search_params = []

            if not indexer["capabilities"].get("tvSearchParams"):
                supports_tv_search = False
            else:
                supports_tv_search = True
                tv_search_params = indexer["capabilities"]["tvSearchParams"]

            if not indexer["capabilities"].get("movieSearchParams"):
                supports_movie_search = False
            else:
                supports_movie_search = True
                movie_search_params = indexer["capabilities"]["movieSearchParams"]

            indexer_info = IndexerInfo(
                id=indexer["id"],
                name=indexer.get("name", "unknown"),
                supports_tv_search=supports_tv_search,
                supports_tv_search_tmdb="tmdbId" in tv_search_params,
                supports_tv_search_imdb="imdbId" in tv_search_params,
                supports_tv_search_tvdb="tvdbId" in tv_search_params,
                supports_tv_search_season="season" in tv_search_params,
                supports_tv_search_episode="ep" in tv_search_params,
                supports_movie_search=supports_movie_search,
                supports_movie_search_tmdb="tmdbId" in movie_search_params,
                supports_movie_search_imdb="imdbId" in movie_search_params,
                supports_movie_search_tvdb="tvdbId" in movie_search_params,
            )
            indexer_info_list.append(indexer_info)
        return indexer_info_list

    def _get_tv_indexers(self) -> list[IndexerInfo]:
        return [x for x in self._get_indexers() if x.supports_tv_search]

    def _get_movie_indexers(self) -> list[IndexerInfo]:
        return [x for x in self._get_indexers() if x.supports_movie_search]

    def _search_indexer_safely(
        self,
        indexer: IndexerInfo,
        parameters: dict[str, str | int | None],
    ) -> list[IndexerQueryResult]:
        """Keep healthy indexers usable when one upstream source is rate-limited."""
        try:
            return self._newznab_search(parameters=parameters, indexer=indexer)
        except Exception as error:
            log.warning(
                "Prowlarr indexer %s failed (%s); continuing with the remaining indexers",
                indexer.name,
                type(error).__name__,
            )
            self.record_tolerated_failure(describe_indexer_failure(indexer.name, error))
            return []

    def search(self, query: str, is_tv: bool) -> list[IndexerQueryResult]:
        log.info(f"Searching for: {query}")
        params: dict[str, str | int | None] = {
            "q": query,
            "t": "tvsearch" if is_tv else "movie",
        }
        raw_results = []
        indexers = self._get_tv_indexers() if is_tv else self._get_movie_indexers()

        for indexer in indexers:
            raw_results.extend(self._search_indexer_safely(indexer, params))

        return raw_results

    def search_season(
        self, query: str, show: Show, season_number: int
    ) -> list[IndexerQueryResult]:
        indexers = self._get_tv_indexers()

        raw_results = []

        for indexer in indexers:
            log.debug("Preparing search for indexer: " + indexer.name)
            search_params: dict[str, str | int | None] = {
                "cat": "5000",
                "q": query,
                "t": "tvsearch",
            }

            if indexer.supports_tv_search_tmdb and show.metadata_provider == "tmdb":
                search_params["tmdbid"] = show.external_id
            if indexer.supports_tv_search_tvdb and show.metadata_provider == "tvdb":
                search_params["tvdbid"] = show.external_id
            if indexer.supports_tv_search_imdb and show.imdb_id:
                search_params["imdbid"] = show.imdb_id
            if indexer.supports_tv_search_season:
                search_params["season"] = season_number

            raw_results.extend(self._search_indexer_safely(indexer, search_params))

        return raw_results

    def search_movie(self, query: str, movie: Movie) -> list[IndexerQueryResult]:
        indexers = self._get_movie_indexers()

        raw_results = []

        for indexer in indexers:
            log.debug("Preparing search for indexer: " + indexer.name)

            search_params: dict[str, str | int | None] = {
                "cat": "2000",
                "q": query,
                "t": "movie",
            }

            if indexer.supports_movie_search_tmdb and movie.metadata_provider == "tmdb":
                search_params["tmdbid"] = movie.external_id
            if indexer.supports_movie_search_tvdb and movie.metadata_provider == "tvdb":
                search_params["tvdbid"] = movie.external_id
            if indexer.supports_movie_search_imdb and movie.imdb_id:
                search_params["imdbid"] = movie.imdb_id

            raw_results.extend(self._search_indexer_safely(indexer, search_params))

        return raw_results

    def search_episode(
        self,
        query: str,
        show: Show,
        season_number: int,
        episode_number: int,
    ) -> list[IndexerQueryResult]:
        indexers = self._get_tv_indexers()
        raw_results = []

        for indexer in indexers:
            search_params: dict[str, str | int | None] = {
                "cat": "5000",
                "q": query,
                "t": "tvsearch",
            }
            if indexer.supports_tv_search_tmdb and show.metadata_provider == "tmdb":
                search_params["tmdbid"] = show.external_id
            if indexer.supports_tv_search_tvdb and show.metadata_provider == "tvdb":
                search_params["tvdbid"] = show.external_id
            if indexer.supports_tv_search_imdb and show.imdb_id:
                search_params["imdbid"] = show.imdb_id
            if indexer.supports_tv_search_season:
                search_params["season"] = season_number
            if indexer.supports_tv_search_episode:
                search_params["ep"] = episode_number

            raw_results.extend(self._search_indexer_safely(indexer, search_params))

        return raw_results
