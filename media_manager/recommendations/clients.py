import asyncio
import hashlib
import json
import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar, cast
from xml.etree import ElementTree as ET

import httpx
from pydantic import ValidationError

from media_manager.recommendations.config import (
    OllamaRecommendationConfig,
    PlexRecommendationConfig,
    TautulliRecommendationConfig,
)
from media_manager.recommendations.exceptions import (
    OllamaResponseError,
    RecommendationConfigurationError,
    RecommendationProviderError,
)
from media_manager.recommendations.schemas import (
    GeneratedRecommendationBatch,
    HistoryEventType,
    HistorySource,
    LibraryMediaIdentity,
    OllamaChatResponse,
    PlexWebhookEvent,
    SourceHistoryItem,
    SourceMetadata,
    SourceStatistic,
    TasteProfile,
    TautulliApiResponse,
    utc_now,
)

_GUID_PATTERNS = (
    ("tmdb", re.compile(r"(?:tmdb|themoviedb)(?:://|/)(\d+)", re.IGNORECASE)),
    ("tvdb", re.compile(r"(?:tvdb|thetvdb)(?:://|/)(\d+)", re.IGNORECASE)),
    ("imdb", re.compile(r"(?:imdb)(?:://|/)(tt\d+)", re.IGNORECASE)),
)

log = logging.getLogger(__name__)


def _optional_string(value: Any, *, max_length: int = 500) -> str | None:  # noqa: ANN401
    if value is None:
        return None
    result = str(value).strip()
    return result[:max_length] if result else None


def _optional_int(value: Any) -> int | None:  # noqa: ANN401
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return None


def _optional_float(value: Any) -> float | None:  # noqa: ANN401
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _bounded_rating(value: Any) -> float | None:  # noqa: ANN401
    rating = _optional_float(value)
    if rating is None or not 0 <= rating <= 10:
        return None
    return rating


def _epoch_datetime(value: Any) -> datetime | None:  # noqa: ANN401
    timestamp = _optional_float(value)
    if timestamp is None or timestamp < 0:
        return None
    try:
        return datetime.fromtimestamp(timestamp, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:  # noqa: ANN401
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.replace("|", ",").split(",")
    elif isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, Mapping):
                item = item.get("tag") or item.get("name")
            if item is not None:
                parts.append(str(item))
    else:
        return []
    return list(dict.fromkeys(part.strip()[:100] for part in parts if part.strip()))[
        :30
    ]


def _external_ids(row: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    direct_fields = {
        "tmdb": ("tmdb_id", "themoviedb_id"),
        "tvdb": ("tvdb_id", "thetvdb_id"),
        "imdb": ("imdb_id",),
    }
    for provider, fields in direct_fields.items():
        for field in fields:
            value = _optional_string(row.get(field), max_length=128)
            if value:
                result[provider] = value
                break

    raw_guids: list[str] = []
    for field in ("Guid", "guids", "guid", "grandparentGuid", "grandparent_guid"):
        value = row.get(field)
        if isinstance(value, str):
            raw_guids.append(value)
        elif isinstance(value, list):
            for entry in value:
                if isinstance(entry, Mapping):
                    entry = entry.get("id") or entry.get("guid")
                if entry:
                    raw_guids.append(str(entry))
    for guid in raw_guids:
        for provider, pattern in _GUID_PATTERNS:
            match = pattern.search(guid)
            if match:
                result.setdefault(provider, match.group(1))

    plex_id = _optional_string(row.get("ratingKey"), max_length=128)
    if plex_id:
        result["plex"] = plex_id
    return result


def _completion_percent(view_offset: Any, duration: Any) -> float | None:  # noqa: ANN401
    offset = _optional_float(view_offset)
    total = _optional_float(duration)
    if offset is None or total is None or total <= 0:
        return None
    return min(100.0, max(0.0, offset / total * 100))


def _stable_digest(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class _AsyncHttpClient:
    provider_name = "provider"

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float,
        verify_ssl: bool,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.client = client

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            if self.client is not None:
                response = await self.client.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    json=json_body,
                    timeout=self.timeout,
                )
            else:
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                ) as client:
                    response = await client.request(
                        method,
                        url,
                        params=params,
                        headers=headers,
                        json=json_body,
                    )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code
            if status_code in {401, 403}:
                msg = f"{self.provider_name} authentication failed (HTTP {status_code})"
            else:
                msg = f"{self.provider_name} request failed (HTTP {status_code})"
            raise RecommendationProviderError(msg) from error
        except httpx.RequestError as error:
            msg = f"{self.provider_name} server is unreachable"
            raise RecommendationProviderError(msg) from error
        return response


class TautulliClient(_AsyncHttpClient):
    provider_name = "Tautulli"
    _library_cache: ClassVar[
        dict[str, tuple[datetime, list[LibraryMediaIdentity]]]
    ] = {}

    def __init__(
        self,
        config: TautulliRecommendationConfig,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            base_url=str(config.url),
            timeout=config.request_timeout_seconds,
            verify_ssl=config.verify_ssl,
            client=client,
        )
        self.config = config

    async def _command(self, command: str, **parameters: Any) -> Any:  # noqa: ANN401
        if not self.config.enabled or self.config.api_key is None:
            msg = "Tautulli is not configured"
            raise RecommendationConfigurationError(msg)
        params: dict[str, Any] = {
            "apikey": self.config.api_key.get_secret_value(),
            "cmd": command,
            **parameters,
        }
        response = await self._request("GET", "/api/v2", params=params)
        try:
            envelope = TautulliApiResponse.model_validate(response.json()).response
        except (ValueError, ValidationError) as error:
            msg = "Tautulli returned an invalid response"
            raise RecommendationProviderError(msg) from error
        if envelope.get("result") != "success":
            msg = "Tautulli rejected the API request"
            raise RecommendationProviderError(msg)
        return envelope.get("data")

    async def get_history(
        self,
        user_id: str,
        *,
        start: int = 0,
        length: int = 100,
    ) -> list[SourceHistoryItem]:
        payload = await self._command(
            "get_history",
            user_id=user_id,
            grouping=0,
            include_activity=0,
            start=start,
            length=length,
            order_column="date",
            order_dir="desc",
        )
        if isinstance(payload, Mapping):
            rows = payload.get("data", [])
        elif isinstance(payload, list):
            rows = payload
        else:
            rows = []
        if not isinstance(rows, list):
            msg = "Tautulli history data has an invalid shape"
            raise RecommendationProviderError(msg)

        history: list[SourceHistoryItem] = []
        for row in rows:
            item = self._normalize_history_row(row)
            if item is not None:
                history.append(item)
        return history

    async def get_statistics(
        self,
        user_id: str,
        *,
        time_range_days: int = 365,
        count: int = 10,
    ) -> list[SourceStatistic]:
        payload = await self._command(
            "get_home_stats",
            user_id=user_id,
            grouping=1,
            time_range=time_range_days,
            stats_type="plays",
            stats_start=0,
            stats_count=count,
        )
        if not isinstance(payload, list):
            return []

        statistics: list[SourceStatistic] = []
        for section in payload:
            if not isinstance(section, Mapping):
                continue
            category = _optional_string(
                section.get("stat_id") or section.get("stat_title"),
                max_length=100,
            )
            rows = section.get("rows", [])
            if category is None or not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                title = _optional_string(
                    row.get("grandparent_title")
                    or row.get("title")
                    or row.get("full_title")
                )
                if title is None:
                    continue
                statistics.append(
                    SourceStatistic(
                        category=category,
                        title=title,
                        media_type=str(row.get("media_type") or "unknown")[:32],
                        play_count=_optional_int(
                            row.get("total_plays") or row.get("users_watched")
                        )
                        or 0,
                        duration_seconds=_optional_int(row.get("total_duration")) or 0,
                        rating=_bounded_rating(
                            row.get("user_rating") or row.get("rating")
                        ),
                    )
                )
        return statistics[:100]

    async def get_metadata(self, rating_key: str) -> SourceMetadata:
        payload = await self._command("get_metadata", rating_key=rating_key)
        if not isinstance(payload, Mapping):
            return SourceMetadata()
        return SourceMetadata(
            genres=_string_list(payload.get("genres") or payload.get("genre")),
            rating=_bounded_rating(payload.get("user_rating") or payload.get("rating")),
        )

    async def get_library_inventory(
        self,
        *,
        cache_minutes: int = 15,
    ) -> list[LibraryMediaIdentity]:
        api_key = self.config.api_key.get_secret_value() if self.config.api_key else ""
        cache_key = (
            f"{self.base_url}:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"
        )
        cached = self._library_cache.get(cache_key)
        if cached is not None and cached[0] > utc_now():
            return list(cached[1])

        raw_libraries = await self._command("get_libraries")
        if isinstance(raw_libraries, Mapping):
            raw_libraries = raw_libraries.get(
                "libraries", raw_libraries.get("data", [])
            )
        if not isinstance(raw_libraries, list):
            raw_libraries = []

        async def fetch_library(library: object) -> list[LibraryMediaIdentity]:
            if not isinstance(library, Mapping):
                return []
            section_type = str(
                library.get("section_type") or library.get("type") or ""
            ).lower()
            if section_type not in {"movie", "show"}:
                return []
            section_id = _optional_string(
                library.get("section_id") or library.get("section_key"),
                max_length=64,
            )
            if section_id is None:
                return []

            identities: list[LibraryMediaIdentity] = []
            start = 0
            page_size = 1_000
            while start < 25_000:
                payload = await self._command(
                    "get_library_media_info",
                    section_id=section_id,
                    section_type=section_type,
                    start=start,
                    length=page_size,
                    order_column="title",
                    order_dir="asc",
                )
                rows: object = payload
                total: int | None = None
                if isinstance(payload, Mapping):
                    total = _optional_int(
                        payload.get("recordsTotal") or payload.get("recordsFiltered")
                    )
                    rows = payload.get("data", [])
                if not isinstance(rows, list):
                    break
                for row in rows:
                    if not isinstance(row, Mapping):
                        continue
                    title = _optional_string(
                        row.get("title") or row.get("grandparent_title")
                    )
                    if title is None:
                        continue
                    identities.append(
                        LibraryMediaIdentity(
                            media_type=("movie" if section_type == "movie" else "show"),
                            title=title,
                            year=_optional_int(row.get("year")),
                            external_ids=_external_ids(row),
                        )
                    )
                start += len(rows)
                if not rows or len(rows) < page_size or (total and start >= total):
                    break
            return identities

        nested = await asyncio.gather(
            *(fetch_library(library) for library in raw_libraries)
        )
        inventory = [item for group in nested for item in group]
        self._library_cache[cache_key] = (
            utc_now() + timedelta(minutes=max(1, cache_minutes)),
            inventory,
        )
        return list(inventory)

    @staticmethod
    def _normalize_history_row(row: Any) -> SourceHistoryItem | None:  # noqa: ANN401
        if not isinstance(row, Mapping):
            return None
        media_type = str(row.get("media_type") or "").lower()
        if media_type not in {"movie", "episode", "show"}:
            return None
        title = _optional_string(
            row.get("title") or row.get("full_title") or row.get("parent_title")
        )
        watched_at = _epoch_datetime(
            row.get("date") or row.get("stopped") or row.get("started")
        )
        if title is None or watched_at is None:
            return None

        event_id = _optional_string(row.get("row_id"), max_length=128)
        if event_id is None:
            event_id = _stable_digest(
                {
                    "rating_key": row.get("rating_key"),
                    "date": row.get("date"),
                    "user_id": row.get("user_id"),
                }
            )
        play_duration = row.get("play_duration")
        duration = _optional_int(
            play_duration if play_duration not in (None, "") else row.get("duration")
        )
        if duration is not None and duration > 100_000:
            duration //= 1_000
        return SourceHistoryItem(
            source=HistorySource.TAUTULLI,
            source_event_id=event_id,
            source_media_id=_optional_string(row.get("rating_key"), max_length=128),
            media_type=media_type,
            title=title,
            series_title=_optional_string(row.get("grandparent_title")),
            year=_optional_int(row.get("year")),
            genres=_string_list(row.get("genres") or row.get("genre")),
            rating=_bounded_rating(row.get("user_rating") or row.get("rating")),
            watched_at=watched_at,
            watch_duration_seconds=duration,
            completion_percent=_optional_float(row.get("percent_complete")),
            external_ids=_external_ids(row),
        )


class PlexClient(_AsyncHttpClient):
    provider_name = "Plex"
    _library_cache: ClassVar[
        dict[str, tuple[datetime, list[LibraryMediaIdentity]]]
    ] = {}

    def __init__(
        self,
        config: PlexRecommendationConfig,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            base_url=str(config.url),
            timeout=config.request_timeout_seconds,
            verify_ssl=config.verify_ssl,
            client=client,
        )
        self.config = config

    def _headers(self) -> dict[str, str]:
        if not self.config.enabled or self.config.token is None:
            msg = "Plex history is not configured"
            raise RecommendationConfigurationError(msg)
        return {
            "Accept": "application/json",
            "X-Plex-Token": self.config.token.get_secret_value(),
        }

    async def get_history(
        self,
        account_id: str,
        *,
        start: int = 0,
        size: int = 100,
    ) -> list[SourceHistoryItem]:
        response = await self._request(
            "GET",
            "/status/sessions/history/all",
            params={
                "accountID": account_id,
                "sort": "viewedAt:desc",
                "X-Plex-Container-Start": start,
                "X-Plex-Container-Size": size,
            },
            headers=self._headers(),
        )
        rows = self._history_rows(response)
        history: list[SourceHistoryItem] = []
        for row in rows:
            item = self._normalize_history_row(row, account_id)
            if item is not None:
                history.append(item)
        return history

    async def get_watched_library_history(
        self,
        account_id: str,
        *,
        maximum: int = 25_000,
    ) -> list[SourceHistoryItem]:
        """Return real watched-state seeds when Plex playback history is unavailable.

        Some Plex servers expose an empty ``/status/sessions/history/all`` response
        even though library items have ``viewCount``/``lastViewedAt`` metadata. TV
        episode rows are deliberately collapsed to one parent-show item here so a
        watched season does not become dozens of recommendation sources.
        """
        response = await self._request(
            "GET",
            "/library/sections",
            headers=self._headers(),
        )
        sections = self._container_rows(response, "Directory")
        movie_sections = sum(
            str(section.get("type") or "").lower() == "movie" for section in sections
        )
        show_sections = sum(
            str(section.get("type") or "").lower() == "show" for section in sections
        )
        log.info(
            "[Plex] Connected; libraries discovered: TV=%d Movies=%d",
            show_sections,
            movie_sections,
        )

        async def fetch_section(
            section: Mapping[str, Any],
        ) -> tuple[list[SourceHistoryItem], int]:
            section_type = str(section.get("type") or "").lower()
            section_key = _optional_string(section.get("key"), max_length=64)
            if section_type not in {"movie", "show"} or not section_key:
                return [], 0

            if section_type == "movie":
                rows = await self._library_section_rows(
                    section_key,
                    account_id=account_id,
                    maximum=maximum,
                )
                watched: list[SourceHistoryItem] = []
                watched_rows = 0
                for row in rows:
                    if not self._is_watched(row):
                        continue
                    watched_rows += 1
                    item = self._normalize_history_row(row, account_id)
                    if item is not None:
                        watched.append(item)
                return watched, watched_rows

            parent_rows = await self._library_section_rows(
                section_key,
                account_id=account_id,
                maximum=maximum,
            )
            parents_by_key = {
                key: row
                for row in parent_rows
                if (key := _optional_string(row.get("ratingKey"), max_length=128))
            }
            parents_by_title = {
                str(row.get("title") or "").strip().casefold(): row
                for row in parent_rows
                if str(row.get("title") or "").strip()
            }
            episode_rows = await self._library_section_rows(
                section_key,
                account_id=account_id,
                media_type=4,
                maximum=maximum,
            )
            watched_rows = 0
            unique_shows: dict[str, SourceHistoryItem] = {}
            for episode in episode_rows:
                if not self._is_watched(episode):
                    continue
                watched_rows += 1
                parent_key = _optional_string(
                    episode.get("grandparentRatingKey"), max_length=128
                )
                series_title = _optional_string(episode.get("grandparentTitle"))
                parent = parents_by_key.get(parent_key or "")
                if parent is None and series_title:
                    parent = parents_by_title.get(series_title.casefold())

                watched_at = _epoch_datetime(
                    episode.get("viewedAt")
                    or episode.get("lastViewedAt")
                    or episode.get("updatedAt")
                )
                if series_title is None or watched_at is None:
                    continue

                source_row: dict[str, Any] = dict(parent or {})
                source_row.update(
                    {
                        "type": "show",
                        "title": series_title,
                        "ratingKey": parent_key or source_row.get("ratingKey"),
                        "viewedAt": int(watched_at.timestamp()),
                    }
                )
                item = self._normalize_history_row(source_row, account_id)
                if item is None:
                    continue
                identity = (
                    f"plex:{parent_key}"
                    if parent_key
                    else f"title:{series_title.casefold()}:{item.year or ''}"
                )
                current = unique_shows.get(identity)
                if current is None or item.watched_at > current.watched_at:
                    unique_shows[identity] = item
            return list(unique_shows.values()), watched_rows

        nested = await asyncio.gather(*(fetch_section(section) for section in sections))
        watched = [item for items, _raw_count in nested for item in items]
        raw_watched_rows = sum(raw_count for _items, raw_count in nested)
        watched.sort(key=lambda item: item.watched_at, reverse=True)
        unique_series = sum(item.media_type == "show" for item in watched)
        unique_movies = sum(item.media_type == "movie" for item in watched)
        log.info("[Plex] Watched library records: %d", raw_watched_rows)
        log.info("[Plex] Unique watched TV series: %d", unique_series)
        log.info("[Plex] Unique watched movies: %d", unique_movies)
        return watched[:maximum]

    async def _library_section_rows(
        self,
        section_key: str,
        *,
        account_id: str,
        media_type: int | None = None,
        maximum: int = 25_000,
    ) -> list[Mapping[str, Any]]:
        rows: list[Mapping[str, Any]] = []
        page_size = min(1_000, maximum)
        start = 0
        while start < maximum:
            request_size = min(page_size, maximum - start)
            params: dict[str, Any] = {
                "accountID": account_id,
                "includeGuids": 1,
                "X-Plex-Container-Start": start,
                "X-Plex-Container-Size": request_size,
            }
            if media_type is not None:
                params["type"] = media_type
            response = await self._request(
                "GET",
                f"/library/sections/{section_key}/all",
                params=params,
                headers=self._headers(),
            )
            page = self._container_rows(response, "Metadata", "Video", "Directory")
            rows.extend(page)
            start += len(page)
            if not page or len(page) < request_size:
                break
        return rows

    @staticmethod
    def _is_watched(row: Mapping[str, Any]) -> bool:
        return (_optional_int(row.get("viewCount")) or 0) > 0 or any(
            row.get(field) not in (None, "") for field in ("viewedAt", "lastViewedAt")
        )

    async def get_statistics(
        self,
        account_id: str,
        *,
        size: int = 500,
    ) -> list[SourceStatistic]:
        history = await self.get_history(account_id, start=0, size=size)
        aggregates: dict[tuple[str, str], SourceStatistic] = {}
        for item in history:
            title = (
                item.series_title
                if item.media_type == "episode" and item.series_title
                else item.title
            )
            media_type = "show" if item.media_type in {"episode", "show"} else "movie"
            key = (media_type, title)
            statistic = aggregates.get(key)
            if statistic is None:
                statistic = SourceStatistic(
                    category="play_history",
                    title=title,
                    media_type=media_type,
                    play_count=0,
                    duration_seconds=0,
                    rating=item.rating,
                )
                aggregates[key] = statistic
            statistic.play_count += 1
            statistic.duration_seconds += item.watch_duration_seconds or 0
            if item.rating is not None:
                statistic.rating = item.rating
        return sorted(
            aggregates.values(),
            key=lambda statistic: statistic.play_count,
            reverse=True,
        )[:100]

    async def get_metadata(self, rating_key: str) -> SourceMetadata:
        response = await self._request(
            "GET",
            f"/library/metadata/{rating_key}",
            headers=self._headers(),
        )
        rows = self._history_rows(response)
        if not rows:
            return SourceMetadata()
        row = rows[0]
        return SourceMetadata(
            genres=_string_list(row.get("Genre") or row.get("genres")),
            rating=_bounded_rating(row.get("userRating") or row.get("rating")),
        )

    async def get_library_inventory(
        self,
        *,
        cache_minutes: int = 15,
    ) -> list[LibraryMediaIdentity]:
        token = self.config.token.get_secret_value() if self.config.token else ""
        cache_key = f"{self.base_url}:{hashlib.sha256(token.encode()).hexdigest()[:16]}"
        cached = self._library_cache.get(cache_key)
        if cached is not None and cached[0] > utc_now():
            return list(cached[1])

        response = await self._request(
            "GET",
            "/library/sections",
            headers=self._headers(),
        )
        sections = self._container_rows(response, "Directory")

        async def fetch_section(
            section: Mapping[str, Any],
        ) -> list[LibraryMediaIdentity]:
            section_type = str(section.get("type") or "").lower()
            if section_type not in {"movie", "show"}:
                return []
            section_key = _optional_string(section.get("key"), max_length=64)
            if not section_key:
                return []
            payload = await self._request(
                "GET",
                f"/library/sections/{section_key}/all",
                params={"includeGuids": 1},
                headers=self._headers(),
            )
            rows = self._container_rows(payload, "Metadata", "Video", "Directory")
            identities: list[LibraryMediaIdentity] = []
            for row in rows:
                title = _optional_string(row.get("title"))
                if not title:
                    continue
                identities.append(
                    LibraryMediaIdentity(
                        media_type="movie" if section_type == "movie" else "show",
                        title=title,
                        year=_optional_int(row.get("year")),
                        external_ids=_external_ids(row),
                    )
                )
            return identities

        nested = await asyncio.gather(*(fetch_section(section) for section in sections))
        inventory = [item for group in nested for item in group]
        self._library_cache[cache_key] = (
            utc_now() + timedelta(minutes=max(1, cache_minutes)),
            inventory,
        )
        return list(inventory)

    @staticmethod
    def _history_rows(response: httpx.Response) -> list[Mapping[str, Any]]:
        return PlexClient._container_rows(response, "Metadata", "Video")

    @staticmethod
    def _container_rows(
        response: httpx.Response,
        *row_names: str,
    ) -> list[Mapping[str, Any]]:
        try:
            payload = response.json()
        except ValueError:
            return PlexClient._xml_rows(response.text, set(row_names))

        if not isinstance(payload, Mapping):
            return []
        container = payload.get("MediaContainer", payload)
        if not isinstance(container, Mapping):
            return []
        rows: object = []
        for row_name in row_names:
            candidate = container.get(row_name)
            if candidate:
                rows = candidate
                break
        if isinstance(rows, Mapping):
            rows = [rows]
        if not isinstance(rows, list):
            return []
        return [
            cast(Mapping[str, Any], row) for row in rows if isinstance(row, Mapping)
        ]

    @staticmethod
    def _xml_rows(
        payload: str,
        row_names: set[str] | None = None,
    ) -> list[Mapping[str, Any]]:
        try:
            root = ET.fromstring(payload)  # noqa: S314
        except ET.ParseError as error:
            msg = "Plex returned an invalid response"
            raise RecommendationProviderError(msg) from error
        rows: list[Mapping[str, Any]] = []
        for element in root:
            if element.tag not in (row_names or {"Video", "Metadata"}):
                continue
            row: dict[str, Any] = dict(element.attrib)
            genres = [
                child.attrib.get("tag", "") for child in element if child.tag == "Genre"
            ]
            if genres:
                row["genres"] = genres
            guids = [
                child.attrib.get("id", "") for child in element if child.tag == "Guid"
            ]
            if guids:
                row["guids"] = guids
            rows.append(row)
        return rows

    @staticmethod
    def _normalize_history_row(
        row: Mapping[str, Any],
        account_id: str,
    ) -> SourceHistoryItem | None:
        media_type = str(row.get("type") or row.get("media_type") or "").lower()
        if media_type not in {"movie", "episode", "show"}:
            return None
        title = _optional_string(row.get("title"))
        watched_at = _epoch_datetime(
            row.get("viewedAt") or row.get("lastViewedAt") or row.get("updatedAt")
        )
        if title is None or watched_at is None:
            return None
        rating_key = _optional_string(row.get("ratingKey"), max_length=128)
        event_id = _stable_digest(
            {
                "account_id": account_id,
                "rating_key": rating_key,
                "viewed_at": watched_at.timestamp(),
                "history_key": row.get("historyKey"),
            }
        )
        duration_ms = _optional_int(row.get("duration"))
        view_offset_ms = _optional_int(row.get("viewOffset"))
        return SourceHistoryItem(
            source=HistorySource.PLEX,
            source_event_id=event_id,
            source_media_id=rating_key,
            media_type=media_type,
            title=title,
            series_title=_optional_string(row.get("grandparentTitle")),
            year=_optional_int(row.get("year")),
            genres=_string_list(row.get("Genre") or row.get("genres")),
            rating=_bounded_rating(row.get("userRating") or row.get("rating")),
            watched_at=watched_at,
            watch_duration_seconds=(
                view_offset_ms // 1_000 if view_offset_ms is not None else None
            ),
            completion_percent=_completion_percent(view_offset_ms, duration_ms),
            external_ids=_external_ids(row),
        )

    @staticmethod
    def parse_webhook(payload: Mapping[str, Any]) -> PlexWebhookEvent | None:
        event = _optional_string(payload.get("event"), max_length=100)
        if event not in {"media.scrobble", "media.rate"}:
            return None
        account = payload.get("Account", {})
        server = payload.get("Server", {})
        metadata = payload.get("Metadata", {})
        if not isinstance(account, Mapping) or not isinstance(metadata, Mapping):
            return None
        if not isinstance(server, Mapping):
            server = {}

        title = _optional_string(metadata.get("title"))
        if title is None:
            return None
        media_type = str(metadata.get("type") or "").lower()
        if media_type not in {"movie", "episode", "show"}:
            return None

        account_id = _optional_string(account.get("id"), max_length=128)
        account_name = _optional_string(account.get("title"), max_length=320)
        watched_at = (
            _epoch_datetime(
                metadata.get("viewedAt")
                or metadata.get("lastViewedAt")
                or metadata.get("updatedAt")
            )
            or utc_now()
        )
        rating_key = _optional_string(metadata.get("ratingKey"), max_length=128)
        digest_payload = {
            "event": event,
            "account_id": account_id,
            "server_id": server.get("uuid"),
            "rating_key": rating_key,
            "viewed_at": metadata.get("viewedAt") or metadata.get("lastViewedAt"),
            "updated_at": metadata.get("updatedAt"),
            "view_offset": metadata.get("viewOffset"),
            "user_rating": metadata.get("userRating"),
        }
        duration_ms = _optional_int(metadata.get("duration"))
        view_offset_ms = _optional_int(metadata.get("viewOffset"))
        history_item = SourceHistoryItem(
            source=HistorySource.PLEX,
            source_event_id=_stable_digest(digest_payload),
            source_media_id=rating_key,
            event_type=(
                HistoryEventType.RATING
                if event == "media.rate"
                else HistoryEventType.WATCH
            ),
            media_type=media_type,
            title=title,
            series_title=_optional_string(metadata.get("grandparentTitle")),
            year=_optional_int(metadata.get("year")),
            genres=_string_list(metadata.get("Genre") or metadata.get("genres")),
            rating=_bounded_rating(
                metadata.get("userRating") or metadata.get("rating")
            ),
            watched_at=watched_at,
            watch_duration_seconds=(
                view_offset_ms // 1_000 if view_offset_ms is not None else None
            ),
            completion_percent=_completion_percent(view_offset_ms, duration_ms),
            external_ids=_external_ids(metadata),
        )
        return PlexWebhookEvent(
            event=event,
            account_id=account_id,
            account_name=account_name,
            server_id=_optional_string(server.get("uuid"), max_length=128),
            history_item=history_item,
        )


class OllamaClient(_AsyncHttpClient):
    provider_name = "Ollama"

    def __init__(
        self,
        config: OllamaRecommendationConfig,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            base_url=str(config.url),
            timeout=config.request_timeout_seconds,
            verify_ssl=config.verify_ssl,
            client=client,
        )
        self.config = config

    async def generate_recommendations(
        self,
        profile: TasteProfile,
        count: int,
        *,
        excluded_titles: list[tuple[str, str]] | None = None,
    ) -> GeneratedRecommendationBatch:
        if not self.config.enabled:
            msg = "Ollama is not configured"
            raise RecommendationConfigurationError(msg)
        schema = GeneratedRecommendationBatch.model_json_schema()
        prompt = {
            "task": "Recommend new media the viewer has not already watched or just received",
            "recommendation_count": count,
            "taste_profile": profile.model_dump(mode="json"),
            "previous_recommendations_to_exclude": [
                {"media_type": media_type, "title": title}
                for media_type, title in (excluded_titles or [])
            ],
            "requirements": [
                "Return only real movies or TV shows",
                "Do not recommend any title already present in watched",
                "Do not return any title in previous_recommendations_to_exclude",
                "Give a concise, taste-specific reason for every item",
                "Use confidence between 0 and 1",
            ],
            "response_json_schema": schema,
        }
        headers = {"Content-Type": "application/json"}
        if self.config.api_key is not None:
            headers["Authorization"] = (
                f"Bearer {self.config.api_key.get_secret_value()}"
            )
        api_path = "/chat" if self.base_url.endswith("/api") else "/api/chat"
        response = await self._request(
            "POST",
            api_path,
            headers=headers,
            json_body={
                "model": self.config.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a private media recommendation engine. "
                            "Follow the supplied JSON schema exactly and never include "
                            "personal identifiers or text outside the JSON object."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(prompt, ensure_ascii=False),
                    },
                ],
                "format": schema,
                "stream": False,
                "keep_alive": self.config.keep_alive,
                "options": {"temperature": 0.25},
            },
        )
        if len(response.content) > self.config.max_response_bytes:
            msg = "Ollama response exceeded the configured size limit"
            raise OllamaResponseError(msg)
        try:
            chat_response = OllamaChatResponse.model_validate(response.json())
            if not chat_response.done:
                msg = "Ollama returned an incomplete response"
                raise OllamaResponseError(msg)
            batch = GeneratedRecommendationBatch.model_validate_json(
                chat_response.message.content
            )
        except (ValueError, ValidationError) as error:
            msg = "Ollama returned invalid structured output"
            raise OllamaResponseError(msg) from error
        if len(batch.recommendations) > count:
            batch.recommendations = batch.recommendations[:count]
        return batch
