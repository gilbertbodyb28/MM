import logging
from collections.abc import Mapping
from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from media_manager.config import MediaManagerConfig
from media_manager.discover.schemas import (
    DiscoverCategory,
    DiscoverGenre,
    DiscoverSort,
    MediaType,
    TimeWindow,
)
from media_manager.metadataProvider.tmdb_transport import (
    TmdbTransport,
    TmdbTransportError,
)

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60.0


class DiscoverProviderError(RuntimeError):
    """Raised when the configured metadata relay cannot serve Discover data."""


class RelayPage(BaseModel):
    page: int = Field(default=1, ge=1)
    total_pages: int = Field(default=0, ge=0)
    total_results: int = Field(default=0, ge=0)
    results: list[dict[str, Any]] = Field(default_factory=list)


class RelayGenreResponse(BaseModel):
    genres: list[DiscoverGenre] = Field(default_factory=list)


class TmdbDiscoverProvider:
    """Typed client for the TMDB endpoints exposed by metadata-relay."""

    name = "tmdb"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        relay_url: str | None = None,
        default_language: str | None = None,
    ) -> None:
        config = MediaManagerConfig().metadata.tmdb
        explicit_relay = relay_url is not None
        relay_url = relay_url or config.tmdb_relay_url
        default_language = default_language or config.default_language
        self.default_language = default_language
        self._client = client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        self._owns_client = client is None
        self._transport = TmdbTransport(
            client=self._client,
            relay_url=relay_url,
            api_key=None if explicit_relay else config.api_key,
            access_token=None if explicit_relay else config.access_token,
            force_relay=explicit_relay,
        )
        self.url = self._transport.base_url

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _get(
        self, path: str, params: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            payload = await self._transport.get(
                path,
                params,
                request_timeout=DEFAULT_TIMEOUT,
            )
        except TmdbTransportError as exc:
            log.exception("TMDB metadata request failed for %s", path)
            msg = "The TMDB metadata request failed."
            raise DiscoverProviderError(msg) from exc

        if not isinstance(payload, dict):
            msg = "The TMDB metadata relay returned an invalid response."
            raise DiscoverProviderError(msg)
        return payload

    async def _get_page(
        self, path: str, params: Mapping[str, Any] | None = None
    ) -> RelayPage:
        payload = await self._get(path, params)
        try:
            return RelayPage.model_validate(payload)
        except ValidationError as exc:
            msg = "The TMDB metadata relay returned an invalid page."
            raise DiscoverProviderError(msg) from exc

    async def get_category(
        self,
        category: DiscoverCategory,
        media_type: MediaType,
        *,
        page: int = 1,
        language: str | None = None,
        region: str | None = None,
        time_window: TimeWindow = TimeWindow.DAY,
    ) -> RelayPage:
        if category is DiscoverCategory.DISCOVER:
            return await self.discover(
                media_type,
                page=page,
                language=language,
                region=region,
            )

        resource = "movies" if media_type is MediaType.MOVIE else "tv"
        return await self._get_page(
            f"/{resource}/{category.value.replace('_', '-')}",
            {
                "page": page,
                "language": language or self.default_language,
                "region": region,
                "time_window": time_window.value
                if category is DiscoverCategory.TRENDING
                else None,
            },
        )

    async def discover(
        self,
        media_type: MediaType,
        *,
        page: int = 1,
        language: str | None = None,
        region: str | None = None,
        year: int | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        release_date_from: date | None = None,
        genres: list[int] | None = None,
        rating_min: float | None = None,
        rating_max: float | None = None,
        sort_by: DiscoverSort = DiscoverSort.POPULARITY_DESC,
        include_adult: bool = False,
    ) -> RelayPage:
        return await self._get_page(
            f"/discover/{media_type.value}",
            {
                "page": page,
                "language": language or self.default_language,
                "region": region,
                "year": year,
                "year_from": year_from,
                "year_to": year_to,
                "release_date_from": release_date_from.isoformat()
                if release_date_from
                else None,
                "genres": ",".join(str(genre_id) for genre_id in genres)
                if genres
                else None,
                "rating_min": rating_min,
                "rating_max": rating_max,
                "sort_by": sort_by.value,
                "include_adult": include_adult,
            },
        )

    async def search(
        self,
        media_type: MediaType,
        query: str,
        *,
        page: int = 1,
        language: str | None = None,
        year: int | None = None,
        include_adult: bool = False,
    ) -> RelayPage:
        resource = "movies" if media_type is MediaType.MOVIE else "tv"
        return await self._get_page(
            f"/{resource}/search",
            {
                "query": query,
                "page": page,
                "language": language or self.default_language,
                "year": year,
                "include_adult": include_adult,
            },
        )

    async def get_genres(
        self, media_type: MediaType, language: str | None = None
    ) -> list[DiscoverGenre]:
        payload = await self._get(
            f"/genres/{media_type.value}",
            {"language": language or self.default_language},
        )
        try:
            return RelayGenreResponse.model_validate(payload).genres
        except ValidationError as exc:
            msg = "The TMDB metadata relay returned an invalid genre list."
            raise DiscoverProviderError(msg) from exc
