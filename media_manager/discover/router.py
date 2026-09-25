from typing import Annotated

from fastapi import APIRouter, Depends, Query

from media_manager.auth.users import current_active_user
from media_manager.discover.dependencies import discover_service_dep
from media_manager.discover.schemas import (
    DiscoverCategory,
    DiscoverGenre,
    DiscoverPage,
    DiscoverSort,
    MediaType,
    TimeWindow,
)

PageQuery = Annotated[int, Query(ge=1, le=500)]
YearQuery = Annotated[int | None, Query(ge=1000, le=9999)]
RatingMinQuery = Annotated[float | None, Query(ge=0, le=10)]
RatingMaxQuery = Annotated[float | None, Query(ge=0, le=10)]
GenreQuery = Annotated[list[int] | None, Query()]
LanguageQuery = Annotated[str | None, Query(min_length=2, max_length=12)]
RegionQuery = Annotated[str | None, Query(min_length=2, max_length=2)]

router = APIRouter(dependencies=[Depends(current_active_user)])


@router.get("")
async def discover_media(
    discover_service: discover_service_dep,
    media_type: MediaType = MediaType.MOVIE,
    category: DiscoverCategory = DiscoverCategory.DISCOVER,
    page: PageQuery = 1,
    year: YearQuery = None,
    year_from: YearQuery = None,
    year_to: YearQuery = None,
    genres: GenreQuery = None,
    rating_min: RatingMinQuery = None,
    rating_max: RatingMaxQuery = None,
    sort_by: DiscoverSort = DiscoverSort.POPULARITY_DESC,
    include_adult: bool = False,
    language: LanguageQuery = None,
    region: RegionQuery = None,
    time_window: TimeWindow = TimeWindow.DAY,
) -> DiscoverPage:
    """Browse TMDB using category, year, genre, rating and sorting filters."""
    return await discover_service.discover(
        media_type,
        category=category,
        page=page,
        language=language,
        region=region,
        year=year,
        year_from=year_from,
        year_to=year_to,
        genres=genres,
        rating_min=rating_min,
        rating_max=rating_max,
        sort_by=sort_by,
        include_adult=include_adult,
        time_window=time_window,
    )


@router.get("/search")
async def search_media(
    query: Annotated[str, Query(min_length=1, max_length=200)],
    discover_service: discover_service_dep,
    media_type: MediaType = MediaType.MOVIE,
    page: PageQuery = 1,
    year: YearQuery = None,
    year_from: YearQuery = None,
    year_to: YearQuery = None,
    genres: GenreQuery = None,
    rating_min: RatingMinQuery = None,
    rating_max: RatingMaxQuery = None,
    sort_by: DiscoverSort = DiscoverSort.POPULARITY_DESC,
    include_adult: bool = False,
    language: LanguageQuery = None,
) -> DiscoverPage:
    """Search titles and apply Discover's year, genre, rating and sort filters."""
    return await discover_service.search(
        media_type,
        query,
        page=page,
        language=language,
        year=year,
        year_from=year_from,
        year_to=year_to,
        genres=genres,
        rating_min=rating_min,
        rating_max=rating_max,
        sort_by=sort_by,
        include_adult=include_adult,
    )


@router.get("/trending")
async def get_trending(
    discover_service: discover_service_dep,
    media_type: MediaType = MediaType.MOVIE,
    page: PageQuery = 1,
    time_window: TimeWindow = TimeWindow.DAY,
    language: LanguageQuery = None,
    region: RegionQuery = None,
) -> DiscoverPage:
    return await discover_service.get_category(
        DiscoverCategory.TRENDING,
        media_type,
        page=page,
        language=language,
        region=region,
        time_window=time_window,
    )


@router.get("/popular")
async def get_popular(
    discover_service: discover_service_dep,
    media_type: MediaType = MediaType.MOVIE,
    page: PageQuery = 1,
    language: LanguageQuery = None,
    region: RegionQuery = None,
) -> DiscoverPage:
    return await discover_service.get_category(
        DiscoverCategory.POPULAR,
        media_type,
        page=page,
        language=language,
        region=region,
    )


@router.get("/upcoming")
async def get_upcoming(
    discover_service: discover_service_dep,
    media_type: MediaType = MediaType.MOVIE,
    page: PageQuery = 1,
    language: LanguageQuery = None,
    region: RegionQuery = None,
) -> DiscoverPage:
    return await discover_service.get_category(
        DiscoverCategory.UPCOMING,
        media_type,
        page=page,
        language=language,
        region=region,
    )


@router.get("/top-rated")
async def get_top_rated(
    discover_service: discover_service_dep,
    media_type: MediaType = MediaType.MOVIE,
    page: PageQuery = 1,
    language: LanguageQuery = None,
    region: RegionQuery = None,
) -> DiscoverPage:
    return await discover_service.get_category(
        DiscoverCategory.TOP_RATED,
        media_type,
        page=page,
        language=language,
        region=region,
    )


@router.get("/genres")
async def get_genres(
    discover_service: discover_service_dep,
    media_type: MediaType = MediaType.MOVIE,
    language: LanguageQuery = None,
) -> list[DiscoverGenre]:
    return await discover_service.get_genres(media_type, language)
