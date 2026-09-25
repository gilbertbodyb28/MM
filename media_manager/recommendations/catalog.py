import logging
from collections.abc import Mapping
from datetime import date
from typing import Any, Literal

import httpx

from media_manager.config import MediaManagerConfig
from media_manager.metadataProvider.tmdb_transport import (
    TmdbTransport,
    TmdbTransportError,
)
from media_manager.recommendations.exceptions import RecommendationProviderError
from media_manager.recommendations.schemas import (
    RecommendationCandidate,
    RecommendationSource,
    normalized_title,
)

log = logging.getLogger(__name__)


class TmdbRecommendationCatalog:
    """Fetch source-related TMDB candidates without exposing TMDB credentials."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        relay_url: str | None = None,
        default_language: str | None = None,
    ) -> None:
        config = MediaManagerConfig().metadata.tmdb
        explicit_relay = relay_url is not None
        self.default_language = default_language or config.default_language
        self._client = client or httpx.AsyncClient(timeout=60)
        self._transport = TmdbTransport(
            client=self._client,
            relay_url=relay_url or config.tmdb_relay_url,
            api_key=None if explicit_relay else config.api_key,
            access_token=None if explicit_relay else config.access_token,
            force_relay=explicit_relay,
        )

    async def resolve_source(
        self,
        source: RecommendationSource,
    ) -> tuple[int, list[int]] | None:
        tmdb_id = self._positive_int(source.external_ids.get("tmdb"))
        if tmdb_id is None:
            tmdb_id = await self._search_source(source)
        if tmdb_id is None:
            return None

        resource = "movies" if source.media_type == "movie" else "tv/shows"
        payload = await self._get(f"/{resource}/{tmdb_id}")
        genres = payload.get("genres", [])
        genre_ids = [
            genre_id
            for genre in genres
            if isinstance(genre, Mapping)
            and (genre_id := self._positive_int(genre.get("id"))) is not None
        ]
        return tmdb_id, genre_ids

    async def candidates_for_source(
        self,
        source: RecommendationSource,
        *,
        candidate_budget: int,
    ) -> tuple[list[RecommendationCandidate], int]:
        resolved = await self.resolve_source(source)
        if resolved is None:
            return [], 0
        tmdb_id, source_genre_ids = resolved
        source.external_ids.setdefault("tmdb", str(tmdb_id))
        candidates: list[RecommendationCandidate] = []
        seen: set[int] = set()
        considered = 0

        async def append_pages(
            path: str,
            *,
            maximum_pages: int = 25,
            extra_params: Mapping[str, Any] | None = None,
        ) -> None:
            nonlocal considered
            page = 1
            total_pages = 1
            while (
                page <= min(total_pages, maximum_pages)
                and considered < candidate_budget
            ):
                payload = await self._get(
                    path,
                    {
                        "page": page,
                        "language": self.default_language,
                        **dict(extra_params or {}),
                    },
                )
                total_pages = min(
                    self._positive_int(payload.get("total_pages")) or 1,
                    maximum_pages,
                )
                rows = payload.get("results", [])
                if not isinstance(rows, list):
                    break
                for row in rows:
                    if considered >= candidate_budget:
                        break
                    considered += 1
                    candidate = self._candidate(row, source.media_type)
                    if candidate is None or candidate.external_id in seen:
                        continue
                    if candidate.external_id == tmdb_id:
                        continue
                    seen.add(candidate.external_id)
                    candidates.append(candidate)
                page += 1

        resource = "movies" if source.media_type == "movie" else "tv/shows"
        await append_pages(f"/{resource}/{tmdb_id}/recommendations")
        if considered < candidate_budget:
            await append_pages(f"/{resource}/{tmdb_id}/similar")
        if considered < candidate_budget and source_genre_ids:
            discover_type = "movie" if source.media_type == "movie" else "tv"
            await append_pages(
                f"/discover/{discover_type}",
                maximum_pages=25,
                extra_params={
                    "genres": ",".join(str(item) for item in source_genre_ids),
                    "sort_by": "vote_count.desc",
                    "include_adult": False,
                },
            )

        source_genres = set(source_genre_ids)
        candidates.sort(
            key=lambda item: self._score_candidate(item, source, source_genres),
            reverse=True,
        )
        return candidates, considered

    async def _search_source(self, source: RecommendationSource) -> int | None:
        resource = "movies" if source.media_type == "movie" else "tv"
        payload = await self._get(
            f"/{resource}/search",
            {
                "query": source.title,
                "year": source.year,
                "language": self.default_language,
                "include_adult": False,
            },
        )
        rows = payload.get("results", [])
        if not isinstance(rows, list):
            return None
        source_title = normalized_title(source.title)
        matches = [
            row
            for row in rows
            if isinstance(row, Mapping)
            and normalized_title(str(row.get("title") or row.get("name") or ""))
            == source_title
        ]
        if not matches:
            return None
        best = min(
            matches,
            key=lambda row: abs(
                (self._year(row, source.media_type) or 10_000)
                - (source.year or self._year(row, source.media_type) or 10_000)
            ),
        )
        return self._positive_int(best.get("id"))

    async def _get(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await self._transport.get(path, params, request_timeout=60)
        except TmdbTransportError as error:
            log.warning("TMDB recommendation request failed for %s", path)
            msg = "TMDB recommendation metadata is currently unavailable."
            raise RecommendationProviderError(msg) from error

    @classmethod
    def _candidate(
        cls,
        row: object,
        media_type: Literal["movie", "show"],
    ) -> RecommendationCandidate | None:
        if not isinstance(row, Mapping):
            return None
        external_id = cls._positive_int(row.get("id"))
        name = str(row.get("title") or row.get("name") or "").strip()
        if external_id is None or not name:
            return None
        raw_genres = row.get("genre_ids", [])
        genre_ids = (
            [
                genre_id
                for raw in raw_genres
                if (genre_id := cls._positive_int(raw)) is not None
            ]
            if isinstance(raw_genres, list)
            else []
        )
        return RecommendationCandidate(
            external_id=external_id,
            media_type=media_type,
            name=name,
            year=cls._year(row, media_type),
            poster_path=(
                str(row.get("poster_path")).strip()
                if row.get("poster_path")
                else None
            ),
            genre_ids=genre_ids,
            original_language=(
                str(row.get("original_language")).strip() or None
                if row.get("original_language") is not None
                else None
            ),
            vote_average=cls._float(row.get("vote_average"), minimum=0, maximum=10),
            popularity=cls._float(row.get("popularity"), minimum=0),
        )

    @staticmethod
    def _score_candidate(
        candidate: RecommendationCandidate,
        source: RecommendationSource,
        source_genres: set[int],
    ) -> float:
        shared_genres = len(source_genres.intersection(candidate.genre_ids))
        year_proximity = 0.0
        if source.year is not None and candidate.year is not None:
            year_proximity = max(0.0, 1.0 - abs(source.year - candidate.year) / 35)
        rating = (candidate.vote_average or 0) / 10
        popularity = min(candidate.popularity or 0, 250) / 250
        source_affinity = min(source.play_count, 10) / 10
        rating_affinity = (source.rating or 0) / 10
        poster_bonus = 0.15 if candidate.poster_path else 0
        return (
            shared_genres * 2.5
            + rating * 1.6
            + popularity
            + year_proximity
            + source_affinity * 0.35
            + rating_affinity * 0.35
            + poster_bonus
        )

    @staticmethod
    def _year(row: Mapping[str, Any], media_type: str) -> int | None:
        raw = row.get("release_date" if media_type == "movie" else "first_air_date")
        if not isinstance(raw, str) or not raw:
            return None
        try:
            return date.fromisoformat(raw).year
        except ValueError:
            try:
                return int(raw[:4])
            except (TypeError, ValueError):
                return None

    @staticmethod
    def _positive_int(value: object) -> int | None:
        try:
            parsed = int(str(value))
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _float(
        value: object,
        *,
        minimum: float,
        maximum: float | None = None,
    ) -> float | None:
        try:
            parsed = float(str(value))
        except (TypeError, ValueError):
            return None
        if parsed < minimum or (maximum is not None and parsed > maximum):
            return None
        return parsed
