import logging
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any, Never

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from media_manager.discover.provider import (
    DiscoverProviderError,
    RelayPage,
    TmdbDiscoverProvider,
)
from media_manager.discover.schemas import (
    DiscoverCategory,
    DiscoverGenre,
    DiscoverMediaItem,
    DiscoverPage,
    DiscoverSort,
    MediaType,
    TimeWindow,
)
from media_manager.movies.models import Movie
from media_manager.tv.models import Show

log = logging.getLogger(__name__)

TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p"


class DiscoverService:
    def __init__(
        self,
        provider: TmdbDiscoverProvider,
        db_session: AsyncSession | None,
    ) -> None:
        self.provider = provider
        self.db_session = db_session

    async def get_category(
        self,
        category: DiscoverCategory,
        media_type: MediaType,
        *,
        page: int = 1,
        language: str | None = None,
        region: str | None = None,
        time_window: TimeWindow = TimeWindow.DAY,
    ) -> DiscoverPage:
        try:
            relay_page = await self.provider.get_category(
                category,
                media_type,
                page=page,
                language=language,
                region=region,
                time_window=time_window,
            )
        except DiscoverProviderError as exc:
            self._raise_bad_gateway(exc)
        return await self._format_page(relay_page, media_type)

    async def discover(
        self,
        media_type: MediaType,
        *,
        category: DiscoverCategory = DiscoverCategory.DISCOVER,
        page: int = 1,
        language: str | None = None,
        region: str | None = None,
        year: int | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        genres: list[int] | None = None,
        rating_min: float | None = None,
        rating_max: float | None = None,
        sort_by: DiscoverSort = DiscoverSort.POPULARITY_DESC,
        include_adult: bool = False,
        time_window: TimeWindow = TimeWindow.DAY,
    ) -> DiscoverPage:
        self._validate_rating_range(rating_min, rating_max)
        self._validate_year_range(year, year_from, year_to)
        advanced_filters = any(
            (
                year is not None,
                year_from is not None,
                year_to is not None,
                bool(genres),
                rating_min is not None,
                rating_max is not None,
                include_adult,
                sort_by is not DiscoverSort.POPULARITY_DESC,
            )
        )
        if category is DiscoverCategory.TRENDING and advanced_filters:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "TMDB's trending feed does not support catalog filters. "
                    "Choose All catalog, Popular, Upcoming, or Top rated."
                ),
            )
        use_discover_endpoint = (
            category is DiscoverCategory.DISCOVER or advanced_filters
        )
        effective_sort = sort_by
        release_date_from: date | None = None
        if category is DiscoverCategory.TOP_RATED and (
            sort_by is DiscoverSort.POPULARITY_DESC
        ):
            effective_sort = DiscoverSort.RATING_DESC
        elif category is DiscoverCategory.UPCOMING:
            release_date_from = datetime.now(UTC).date()
            if sort_by is DiscoverSort.POPULARITY_DESC:
                effective_sort = DiscoverSort.RELEASE_DATE_ASC

        try:
            if use_discover_endpoint:
                relay_page = await self.provider.discover(
                    media_type,
                    page=page,
                    language=language,
                    region=region,
                    year=year,
                    year_from=year_from,
                    year_to=year_to,
                    release_date_from=release_date_from,
                    genres=genres,
                    rating_min=rating_min,
                    rating_max=rating_max,
                    sort_by=effective_sort,
                    include_adult=include_adult,
                )
            else:
                relay_page = await self.provider.get_category(
                    category,
                    media_type,
                    page=page,
                    language=language,
                    region=region,
                    time_window=time_window,
                )
        except DiscoverProviderError as exc:
            self._raise_bad_gateway(exc)

        return await self._format_page(relay_page, media_type)

    async def search(
        self,
        media_type: MediaType,
        query: str,
        *,
        page: int = 1,
        language: str | None = None,
        year: int | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        genres: list[int] | None = None,
        rating_min: float | None = None,
        rating_max: float | None = None,
        sort_by: DiscoverSort = DiscoverSort.POPULARITY_DESC,
        include_adult: bool = False,
    ) -> DiscoverPage:
        normalized_query = query.strip()
        if not normalized_query:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Search query must not be empty.",
            )
        self._validate_rating_range(rating_min, rating_max)
        self._validate_year_range(year, year_from, year_to)

        try:
            relay_page = await self.provider.search(
                media_type,
                normalized_query,
                page=page,
                language=language,
                year=year,
                include_adult=include_adult,
            )
        except DiscoverProviderError as exc:
            self._raise_bad_gateway(exc)

        result = await self._format_page(relay_page, media_type)
        result.results = self._filter_items(
            result.results,
            year=year,
            year_from=year_from,
            year_to=year_to,
            genres=genres,
            rating_min=rating_min,
            rating_max=rating_max,
            include_adult=include_adult,
        )
        result.results = self._sort_items(result.results, sort_by)
        return result

    async def get_genres(
        self, media_type: MediaType, language: str | None = None
    ) -> list[DiscoverGenre]:
        try:
            return await self.provider.get_genres(media_type, language)
        except DiscoverProviderError as exc:
            self._raise_bad_gateway(exc)

    async def _format_page(
        self, relay_page: RelayPage, media_type: MediaType
    ) -> DiscoverPage:
        items: list[DiscoverMediaItem] = []
        for raw_item in relay_page.results:
            item = self._format_item(raw_item, media_type)
            if item is not None:
                items.append(item)
        await self._mark_library_items(items, media_type)
        return DiscoverPage(
            page=relay_page.page,
            total_pages=relay_page.total_pages,
            total_results=relay_page.total_results,
            results=items,
        )

    @staticmethod
    def _format_item(
        raw_item: dict[str, Any], media_type: MediaType
    ) -> DiscoverMediaItem | None:
        external_id = raw_item.get("id")
        name = (
            raw_item.get("title")
            if media_type is MediaType.MOVIE
            else raw_item.get("name")
        )
        original_name = (
            raw_item.get("original_title")
            if media_type is MediaType.MOVIE
            else raw_item.get("original_name")
        )
        if (
            not isinstance(external_id, int)
            or external_id <= 0
            or not isinstance(name, str)
            or not name
        ):
            log.warning("Ignoring malformed TMDB %s result", media_type.value)
            return None

        raw_release_date = (
            raw_item.get("release_date")
            if media_type is MediaType.MOVIE
            else raw_item.get("first_air_date")
        )
        release_date = DiscoverService._parse_date(raw_release_date)
        genre_ids = raw_item.get("genre_ids")
        if not isinstance(genre_ids, list):
            genre_ids = []

        return DiscoverMediaItem(
            external_id=external_id,
            media_type=media_type,
            name=name,
            original_name=original_name if isinstance(original_name, str) else None,
            overview=raw_item.get("overview")
            if isinstance(raw_item.get("overview"), str)
            else None,
            poster_path=DiscoverService._image_url(raw_item.get("poster_path"), "w500"),
            backdrop_path=DiscoverService._image_url(
                raw_item.get("backdrop_path"), "w1280"
            ),
            year=release_date.year if release_date else None,
            release_date=release_date,
            vote_average=DiscoverService._optional_rating(raw_item.get("vote_average")),
            vote_count=DiscoverService._non_negative_int(raw_item.get("vote_count")),
            popularity=DiscoverService._optional_float(raw_item.get("popularity")),
            genre_ids=[
                genre_id
                for genre_id in genre_ids
                if isinstance(genre_id, int) and genre_id > 0
            ],
            original_language=raw_item.get("original_language")
            if isinstance(raw_item.get("original_language"), str)
            else None,
            adult=raw_item.get("adult") is True,
        )

    async def _mark_library_items(
        self, items: list[DiscoverMediaItem], media_type: MediaType
    ) -> None:
        if self.db_session is None or not items:
            return

        model = Movie if media_type is MediaType.MOVIE else Show
        external_ids = {item.external_id for item in items}
        statement = select(model.external_id, model.id).where(
            model.metadata_provider == self.provider.name,
            model.external_id.in_(external_ids),
        )
        rows = (await self.db_session.execute(statement)).all()
        internal_ids = {row[0]: row[1] for row in rows}
        for item in items:
            if item.external_id in internal_ids:
                item.added = True
                item.id = internal_ids[item.external_id]

    @staticmethod
    def _filter_items(
        items: Iterable[DiscoverMediaItem],
        *,
        year: int | None,
        year_from: int | None,
        year_to: int | None,
        genres: list[int] | None,
        rating_min: float | None,
        rating_max: float | None,
        include_adult: bool,
    ) -> list[DiscoverMediaItem]:
        required_genres = set(genres or [])
        return [
            item
            for item in items
            if (year is None or item.year == year)
            and (
                year_from is None or (item.year is not None and item.year >= year_from)
            )
            and (year_to is None or (item.year is not None and item.year <= year_to))
            and (not required_genres or required_genres.issubset(item.genre_ids))
            and (
                rating_min is None
                or (item.vote_average is not None and item.vote_average >= rating_min)
            )
            and (
                rating_max is None
                or (item.vote_average is not None and item.vote_average <= rating_max)
            )
            and (include_adult or not item.adult)
        ]

    @staticmethod
    def _sort_items(
        items: list[DiscoverMediaItem], sort_by: DiscoverSort
    ) -> list[DiscoverMediaItem]:
        field, direction = sort_by.value.split(".", maxsplit=1)
        reverse = direction == "desc"

        def sort_key(item: DiscoverMediaItem) -> tuple[bool, Any]:
            values: dict[str, Any] = {
                "popularity": item.popularity,
                "vote_average": item.vote_average,
                "vote_count": item.vote_count,
                "release_date": item.release_date,
                "title": item.name.casefold(),
            }
            value = values[field]
            if reverse:
                return value is not None, value
            return value is None, value

        return sorted(items, key=sort_key, reverse=reverse)

    @staticmethod
    def _validate_rating_range(
        rating_min: float | None, rating_max: float | None
    ) -> None:
        if (
            rating_min is not None
            and rating_max is not None
            and rating_min > rating_max
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="rating_min must be less than or equal to rating_max.",
            )

    @staticmethod
    def _validate_year_range(
        year: int | None, year_from: int | None, year_to: int | None
    ) -> None:
        invalid_range = (
            year_from is not None and year_to is not None and year_from > year_to
        )
        exact_year_outside_range = year is not None and (
            (year_from is not None and year < year_from)
            or (year_to is not None and year > year_to)
        )
        if invalid_range or exact_year_outside_range:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="year_from must be less than or equal to year_to and include year when provided.",
            )

    @staticmethod
    def _raise_bad_gateway(exc: DiscoverProviderError) -> Never:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The metadata provider is currently unavailable.",
        ) from exc

    @staticmethod
    def _parse_date(value: object) -> date | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _image_url(value: object, size: str) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        if value.startswith(("http://", "https://")):
            return value
        path = value if value.startswith("/") else f"/{value}"
        return f"{TMDB_IMAGE_BASE_URL}/{size}{path}"

    @staticmethod
    def _optional_float(value: object) -> float | None:
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        result = float(value)
        return result if result >= 0 else None

    @staticmethod
    def _optional_rating(value: object) -> float | None:
        result = DiscoverService._optional_float(value)
        return result if result is not None and result <= 10 else None

    @staticmethod
    def _non_negative_int(value: object) -> int:
        return (
            value
            if not isinstance(value, bool) and isinstance(value, int) and value >= 0
            else 0
        )
