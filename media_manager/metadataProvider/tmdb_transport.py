import re
from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import SecretStr

from media_manager.config import MediaManagerConfig

TMDB_API_URL = "https://api.themoviedb.org/3"


class TmdbTransportError(RuntimeError):
    """A sanitized TMDB transport failure that never contains credentials."""


def _secret_value(value: SecretStr | str | None) -> str | None:
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class TmdbTransport:
    """Call either a configured metadata relay or TMDB directly.

    The rest of MediaManager uses a stable relay-shaped path vocabulary.  When
    an administrator stores a TMDB credential in Settings, those paths and
    parameters are translated to TMDB API v3 and no relay container is needed.
    """

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        relay_url: str | None = None,
        api_key: SecretStr | str | None = None,
        access_token: SecretStr | str | None = None,
        force_relay: bool = False,
    ) -> None:
        if relay_url is None and api_key is None and access_token is None:
            config = MediaManagerConfig().metadata.tmdb
            relay_url = config.tmdb_relay_url
            api_key = config.api_key
            access_token = config.access_token

        self._client = client
        self._api_key = _secret_value(api_key)
        self._access_token = _secret_value(access_token)
        self.direct = not force_relay and bool(self._api_key or self._access_token)
        self.base_url = (
            TMDB_API_URL
            if self.direct
            else (relay_url or "https://metadata-relay.dorninger.co/tmdb").rstrip("/")
        )

    async def get(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        request_timeout: float = 60.0,
    ) -> dict[str, Any]:
        request_path = path
        request_params = {
            key: value for key, value in (params or {}).items() if value is not None
        }
        headers: dict[str, str] = {}

        if self.direct:
            request_path, request_params = self._translate_direct_request(
                path, request_params
            )
            if self._access_token:
                headers["Authorization"] = f"Bearer {self._access_token}"
            elif self._api_key:
                request_params["api_key"] = self._api_key

        try:
            response = await self._client.get(
                f"{self.base_url}{request_path}",
                params=request_params,
                headers=headers,
                timeout=request_timeout,
            )
        except httpx.HTTPError as exc:
            msg = "TMDB could not be reached."
            raise TmdbTransportError(msg) from exc

        if response.is_error:
            msg = f"TMDB returned HTTP {response.status_code}."
            raise TmdbTransportError(msg)
        try:
            payload = response.json()
        except ValueError as exc:
            msg = "TMDB returned an invalid response."
            raise TmdbTransportError(msg) from exc
        if not isinstance(payload, dict):
            msg = "TMDB returned an invalid response."
            raise TmdbTransportError(msg)
        return payload

    @staticmethod
    def _translate_direct_request(
        path: str,
        params: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        translated = dict(params)

        if path == "/tv/search":
            year = translated.pop("year", None)
            if year is not None:
                translated["first_air_date_year"] = year
            return "/search/tv", translated
        if path == "/movies/search":
            return "/search/movie", translated
        if path == "/tv/trending":
            window = translated.pop("time_window", "day")
            return f"/trending/tv/{window}", translated
        if path == "/movies/trending":
            window = translated.pop("time_window", "day")
            return f"/trending/movie/{window}", translated

        category_paths = {
            "/tv/popular": "/tv/popular",
            "/tv/upcoming": "/tv/on_the_air",
            "/tv/top-rated": "/tv/top_rated",
            "/movies/popular": "/movie/popular",
            "/movies/upcoming": "/movie/upcoming",
            "/movies/top-rated": "/movie/top_rated",
            "/genres/movie": "/genre/movie/list",
            "/genres/tv": "/genre/tv/list",
        }
        if path in category_paths:
            return category_paths[path], translated

        show_match = re.fullmatch(r"/tv/shows/(\d+)", path)
        if show_match:
            return f"/tv/{show_match.group(1)}", translated
        show_ids_match = re.fullmatch(r"/tv/shows/(\d+)/external_ids", path)
        if show_ids_match:
            return f"/tv/{show_ids_match.group(1)}/external_ids", translated
        show_recommendations_match = re.fullmatch(
            r"/tv/shows/(\d+)/(recommendations|similar)", path
        )
        if show_recommendations_match:
            return (
                f"/tv/{show_recommendations_match.group(1)}/"
                f"{show_recommendations_match.group(2)}",
                translated,
            )
        season_match = re.fullmatch(r"/tv/shows/(\d+)/(\d+)", path)
        if season_match:
            return (
                f"/tv/{season_match.group(1)}/season/{season_match.group(2)}",
                translated,
            )

        movie_match = re.fullmatch(r"/movies/(\d+)", path)
        if movie_match:
            return f"/movie/{movie_match.group(1)}", translated
        movie_ids_match = re.fullmatch(r"/movies/(\d+)/external_ids", path)
        if movie_ids_match:
            return f"/movie/{movie_ids_match.group(1)}/external_ids", translated
        movie_recommendations_match = re.fullmatch(
            r"/movies/(\d+)/(recommendations|similar)", path
        )
        if movie_recommendations_match:
            return (
                f"/movie/{movie_recommendations_match.group(1)}/"
                f"{movie_recommendations_match.group(2)}",
                translated,
            )

        if path in {"/discover/movie", "/discover/tv"}:
            media_type = path.rsplit("/", maxsplit=1)[-1]
            return path, TmdbTransport._translate_discover_params(
                media_type, translated
            )

        return path, translated

    @staticmethod
    def _translate_discover_params(
        media_type: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        translated = dict(params)
        genres = translated.pop("genres", None)
        if genres:
            translated["with_genres"] = genres
        rating_min = translated.pop("rating_min", None)
        if rating_min is not None:
            translated["vote_average.gte"] = rating_min
        rating_max = translated.pop("rating_max", None)
        if rating_max is not None:
            translated["vote_average.lte"] = rating_max

        year = translated.pop("year", None)
        year_from = translated.pop("year_from", None)
        year_to = translated.pop("year_to", None)
        release_date_from = translated.pop("release_date_from", None)
        sort_by = translated.get("sort_by")

        if media_type == "movie":
            if year is not None:
                translated["primary_release_year"] = year
            if year_from is not None:
                translated["primary_release_date.gte"] = f"{int(year_from):04d}-01-01"
            if release_date_from is not None:
                current = translated.get("primary_release_date.gte", "")
                translated["primary_release_date.gte"] = max(
                    current, str(release_date_from)
                )
            if year_to is not None:
                translated["primary_release_date.lte"] = f"{int(year_to):04d}-12-31"
            if sort_by:
                translated["sort_by"] = str(sort_by).replace(
                    "release_date.", "primary_release_date."
                )
        else:
            if year is not None:
                translated["first_air_date_year"] = year
            if year_from is not None:
                translated["first_air_date.gte"] = f"{int(year_from):04d}-01-01"
            if release_date_from is not None:
                current = translated.get("first_air_date.gte", "")
                translated["first_air_date.gte"] = max(
                    current, str(release_date_from)
                )
            if year_to is not None:
                translated["first_air_date.lte"] = f"{int(year_to):04d}-12-31"
            if sort_by:
                translated["sort_by"] = str(sort_by).replace(
                    "release_date.", "first_air_date."
                ).replace("title.", "name.")
        return translated
