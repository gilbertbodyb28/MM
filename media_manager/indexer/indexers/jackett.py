import concurrent
import concurrent.futures
import logging
import xml.etree.ElementTree as ET
from concurrent.futures.thread import ThreadPoolExecutor
from dataclasses import dataclass

import requests

from media_manager.config import MediaManagerConfig
from media_manager.indexer.indexers.generic import GenericIndexer
from media_manager.indexer.indexers.torznab_mixin import TorznabMixin
from media_manager.indexer.schemas import IndexerQueryResult
from media_manager.movies.schemas import Movie
from media_manager.tv.schemas import Show

log = logging.getLogger(__name__)


@dataclass
class IndexerInfo:
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


class Jackett(GenericIndexer, TorznabMixin):
    def __init__(self) -> None:
        """
        A subclass of GenericIndexer for interacting with the Jacket API.

        """
        super().__init__(name="jackett")
        config = MediaManagerConfig().indexers.jackett
        self.api_key = config.api_key
        self.url = config.url
        self.indexers = config.indexers
        self.timeout_seconds = config.timeout_seconds
        self.max_results = config.max_results

    def search(self, query: str, is_tv: bool) -> list[IndexerQueryResult]:
        log.debug("Searching for " + query)

        params: dict[str, str | int] = {
            "q": query,
            "t": "tvsearch" if is_tv else "movie",
        }

        return self.__search_jackett(params)

    def __search_jackett(
        self, params: dict[str, str | int]
    ) -> list[IndexerQueryResult]:
        futures = {}
        with ThreadPoolExecutor() as executor, requests.Session() as session:
            for indexer in self.indexers:
                future = executor.submit(
                    self.get_torrents_by_indexer, indexer, params, session
                )
                futures[future] = indexer

            responses = []

            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    if result is not None:
                        responses.extend(result[: self.max_results])
                except Exception as error:
                    # Request exception messages may contain the full URL, including
                    # Jackett's API key. Keep diagnostics useful without logging it.
                    log.error(  # noqa: TRY400 - exception text may expose the API key
                        "Jackett search failed for indexer %s (%s)",
                        futures[future],
                        type(error).__name__,
                    )

        return responses

    def __get_search_capabilities(
        self, indexer: str, session: requests.Session
    ) -> IndexerInfo:
        endpoint_path = f"/api/v2.0/indexers/{indexer}/results/torznab/api"
        url = f"{self.url}{endpoint_path}"
        response = session.get(
            url,
            params={"apikey": self.api_key, "t": "caps"},
            timeout=self.timeout_seconds,
        )
        if response.status_code != 200:
            msg = f"Cannot get search capabilities for Indexer {indexer}"
            log.error(msg)
            raise RuntimeError(msg)

        xml = response.text
        xml_tree = ET.fromstring(xml)  # noqa: S314  # trusted source, since it is user controlled
        tv_search = xml_tree.find("./*/tv-search")
        movie_search = xml_tree.find("./*/movie-search")
        log.debug(tv_search.attrib if tv_search is not None else {})
        log.debug(movie_search.attrib if movie_search is not None else {})

        tv_search_capabilities = []
        movie_search_capabilities = []
        tv_search_available = (tv_search is not None) and (
            tv_search.attrib["available"] == "yes"
        )
        movie_search_available = (movie_search is not None) and (
            movie_search.attrib["available"] == "yes"
        )

        if tv_search_available:
            tv_search_capabilities = tv_search.attrib["supportedParams"].split(",")

        if movie_search_available:
            movie_search_capabilities = movie_search.attrib["supportedParams"].split(
                ","
            )

        return IndexerInfo(
            supports_tv_search=tv_search_available,
            supports_tv_search_imdb="imdbid" in tv_search_capabilities,
            supports_tv_search_tmdb="tmdbid" in tv_search_capabilities,
            supports_tv_search_tvdb="tvdbid" in tv_search_capabilities,
            supports_tv_search_season="season" in tv_search_capabilities,
            supports_tv_search_episode="ep" in tv_search_capabilities,
            supports_movie_search=movie_search_available,
            supports_movie_search_imdb="imdbid" in movie_search_capabilities,
            supports_movie_search_tmdb="tmdbid" in movie_search_capabilities,
            supports_movie_search_tvdb="tvdbid" in movie_search_capabilities,
        )

    def __get_optimal_query_parameters(
        self,
        indexer: str,
        session: requests.Session,
        params: dict[str, str | int],
    ) -> dict[str, str | int]:
        query_params: dict[str, str | int] = {
            "apikey": self.api_key,
            "t": params["t"],
        }

        search_capabilities = self.__get_search_capabilities(
            indexer=indexer, session=session
        )
        if params["t"] == "tvsearch":
            if not search_capabilities.supports_tv_search:
                msg = f"Indexer {indexer} does not support TV search"
                raise RuntimeError(msg)
            if search_capabilities.supports_tv_search_season and "season" in params:
                query_params["season"] = params["season"]
            if search_capabilities.supports_tv_search_episode and "ep" in params:
                query_params["ep"] = params["ep"]
            if search_capabilities.supports_tv_search_imdb and "imdbid" in params:
                query_params["imdbid"] = params["imdbid"]
            elif search_capabilities.supports_tv_search_tvdb and "tvdbid" in params:
                query_params["tvdbid"] = params["tvdbid"]
            elif search_capabilities.supports_tv_search_tmdb and "tmdbid" in params:
                query_params["tmdbid"] = params["tmdbid"]
            else:
                query_params["q"] = params["q"]
        if params["t"] == "movie":
            if not search_capabilities.supports_movie_search:
                msg = f"Indexer {indexer} does not support Movie search"
                raise RuntimeError(msg)
            if search_capabilities.supports_movie_search_imdb and "imdbid" in params:
                query_params["imdbid"] = params["imdbid"]
            elif search_capabilities.supports_movie_search_tvdb and "tvdbid" in params:
                query_params["tvdbid"] = params["tvdbid"]
            elif search_capabilities.supports_movie_search_tmdb and "tmdbid" in params:
                query_params["tmdbid"] = params["tmdbid"]
            else:
                query_params["q"] = params["q"]
        return query_params

    def get_torrents_by_indexer(
        self,
        indexer: str,
        params: dict[str, str | int],
        session: requests.Session,
    ) -> list[IndexerQueryResult]:
        endpoint_path = f"/api/v2.0/indexers/{indexer}/results/torznab/api"
        url = f"{self.url}{endpoint_path}"
        query_params = self.__get_optimal_query_parameters(
            indexer=indexer, session=session, params=params
        )
        response = session.get(url, timeout=self.timeout_seconds, params=query_params)
        log.debug("Indexer %s requested endpoint %s", indexer, endpoint_path)

        if response.status_code != 200:
            log.error(
                f"Jacket error with indexer {indexer}, error: {response.status_code}"
            )
            return []

        results = self.process_search_result(response.content)[: self.max_results]

        log.info(f"Indexer {indexer} returned {len(results)} results")
        return results

    def search_season(
        self, query: str, show: Show, season_number: int
    ) -> list[IndexerQueryResult]:
        log.debug(f"Searching for season {season_number} of show {show.name}")
        params: dict[str, str | int] = {
            "t": "tvsearch",
            "season": season_number,
            "q": query,
        }
        if show.imdb_id:
            params["imdbid"] = show.imdb_id
        params[show.metadata_provider + "id"] = show.external_id
        return self.__search_jackett(params=params)

    def search_movie(self, query: str, movie: Movie) -> list[IndexerQueryResult]:
        log.debug(f"Searching for movie {movie.name}")
        params: dict[str, str | int] = {
            "t": "movie",
            "q": query,
        }
        if movie.imdb_id:
            params["imdbid"] = movie.imdb_id
        params[movie.metadata_provider + "id"] = movie.external_id
        return self.__search_jackett(params=params)

    def search_episode(
        self,
        query: str,
        show: Show,
        season_number: int,
        episode_number: int,
    ) -> list[IndexerQueryResult]:
        log.debug(
            "Searching for episode %s of season %s of show %s",
            episode_number,
            season_number,
            show.name,
        )
        params: dict[str, str | int] = {
            "t": "tvsearch",
            "season": season_number,
            "ep": episode_number,
            "q": query,
        }
        if show.imdb_id:
            params["imdbid"] = show.imdb_id
        params[show.metadata_provider + "id"] = show.external_id
        return self.__search_jackett(params=params)
