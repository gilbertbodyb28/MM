import logging
import os
from collections.abc import Callable
from datetime import date
from enum import StrEnum
from functools import partial
from typing import Annotated, Any

import tmdbsimple
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool
from tmdbsimple import TV, Discover, Genres, Movies, Search, Trending, TV_Seasons

log = logging.getLogger(__name__)

TMDB_UNAVAILABLE = "TMDB is currently unavailable."
TMDB_NOT_CONFIGURED = "TMDB_API_KEY environment variable is not set."


class MediaType(StrEnum):
    MOVIE = "movie"
    TV = "tv"


class TimeWindow(StrEnum):
    DAY = "day"
    WEEK = "week"


class DiscoverSort(StrEnum):
    POPULARITY_ASC = "popularity.asc"
    POPULARITY_DESC = "popularity.desc"
    RATING_ASC = "vote_average.asc"
    RATING_DESC = "vote_average.desc"
    VOTE_COUNT_ASC = "vote_count.asc"
    VOTE_COUNT_DESC = "vote_count.desc"
    RELEASE_DATE_ASC = "release_date.asc"
    RELEASE_DATE_DESC = "release_date.desc"
    TITLE_ASC = "title.asc"
    TITLE_DESC = "title.desc"


class TmdbPage(BaseModel):
    page: int = Field(default=1, ge=1)
    total_pages: int = Field(default=0, ge=0)
    total_results: int = Field(default=0, ge=0)
    results: list[dict[str, Any]] = Field(default_factory=list)


class TmdbGenre(BaseModel):
    id: int = Field(gt=0)
    name: str = Field(min_length=1)


class TmdbGenreResponse(BaseModel):
    genres: list[TmdbGenre] = Field(default_factory=list)


def require_tmdb_api_key() -> None:
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=TMDB_NOT_CONFIGURED,
        )
    tmdbsimple.API_KEY = api_key


router = APIRouter(
    prefix="/tmdb",
    tags=["TMDB"],
    dependencies=[Depends(require_tmdb_api_key)],
)

if not os.getenv("TMDB_API_KEY"):
    log.warning(TMDB_NOT_CONFIGURED)


async def _call_tmdb(
    call: Callable[..., dict[str, Any]], **kwargs: object
) -> dict[str, Any]:
    try:
        result = await run_in_threadpool(partial(call, **kwargs))
    except Exception as exc:
        log.exception("TMDB request failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=TMDB_UNAVAILABLE,
        ) from exc
    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=TMDB_UNAVAILABLE,
        )
    return result


async def _call_page(call: Callable[..., dict[str, Any]], **kwargs: object) -> TmdbPage:
    payload = await _call_tmdb(call, **kwargs)
    try:
        return TmdbPage.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=TMDB_UNAVAILABLE,
        ) from exc


def _discover_sort(media_type: MediaType, sort_by: DiscoverSort) -> str:
    field, direction = sort_by.value.split(".", maxsplit=1)
    if field == "release_date":
        field = (
            "primary_release_date"
            if media_type is MediaType.MOVIE
            else "first_air_date"
        )
    elif field == "title":
        field = "title" if media_type is MediaType.MOVIE else "name"
    return f"{field}.{direction}"


def _discover_params(
    media_type: MediaType,
    *,
    language: str,
    page: int,
    region: str | None,
    year: int | None,
    year_from: int | None,
    year_to: int | None,
    release_date_from: date | None,
    genres: str | None,
    rating_min: float | None,
    rating_max: float | None,
    sort_by: DiscoverSort,
    include_adult: bool,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "language": language,
        "page": page,
        "sort_by": _discover_sort(media_type, sort_by),
        "include_adult": include_adult,
    }
    if genres:
        params["with_genres"] = genres
    if rating_min is not None:
        params["vote_average.gte"] = rating_min
    if rating_max is not None:
        params["vote_average.lte"] = rating_max

    if media_type is MediaType.MOVIE:
        params["include_video"] = False
        if region:
            params["region"] = region
        if year is not None:
            params["primary_release_year"] = year
        if year_from is not None:
            params["primary_release_date.gte"] = f"{year_from:04d}-01-01"
        if release_date_from is not None:
            existing = params.get("primary_release_date.gte", "")
            params["primary_release_date.gte"] = max(
                existing, release_date_from.isoformat()
            )
        if year_to is not None:
            params["primary_release_date.lte"] = f"{year_to:04d}-12-31"
    else:
        if year is not None:
            params["first_air_date_year"] = year
        if year_from is not None:
            params["first_air_date.gte"] = f"{year_from:04d}-01-01"
        if release_date_from is not None:
            existing = params.get("first_air_date.gte", "")
            params["first_air_date.gte"] = max(existing, release_date_from.isoformat())
        if year_to is not None:
            params["first_air_date.lte"] = f"{year_to:04d}-12-31"
    return params


@router.get("/tv/trending")
async def get_tmdb_trending_tv(
    language: str = "en",
    page: Annotated[int, Query(ge=1, le=500)] = 1,
    time_window: TimeWindow = TimeWindow.DAY,
) -> TmdbPage:
    return await _call_page(
        Trending(media_type="tv", time_window=time_window.value).info,
        language=language,
        page=page,
    )


@router.get("/tv/popular")
async def get_tmdb_popular_tv(
    language: str = "en",
    page: Annotated[int, Query(ge=1, le=500)] = 1,
) -> TmdbPage:
    return await _call_page(TV().popular, language=language, page=page)


@router.get("/tv/upcoming")
async def get_tmdb_upcoming_tv(
    language: str = "en",
    page: Annotated[int, Query(ge=1, le=500)] = 1,
) -> TmdbPage:
    """Return the official TMDB 'on the air' TV list as upcoming shows."""
    return await _call_page(TV().on_the_air, language=language, page=page)


@router.get("/tv/top-rated")
async def get_tmdb_top_rated_tv(
    language: str = "en",
    page: Annotated[int, Query(ge=1, le=500)] = 1,
) -> TmdbPage:
    return await _call_page(TV().top_rated, language=language, page=page)


@router.get("/tv/search")
async def search_tmdb_tv(
    query: Annotated[str, Query(min_length=1, max_length=200)],
    page: Annotated[int, Query(ge=1, le=500)] = 1,
    language: str = "en",
    year: Annotated[int | None, Query(ge=1000, le=9999)] = None,
    include_adult: bool = False,
) -> TmdbPage:
    params: dict[str, Any] = {
        "page": page,
        "query": query,
        "language": language,
        "include_adult": include_adult,
    }
    if year is not None:
        params["first_air_date_year"] = year
    return await _call_page(Search().tv, **params)


@router.get("/tv/shows/{show_id}")
async def get_tmdb_show(show_id: int, language: str = "en") -> dict[str, Any]:
    return await _call_tmdb(TV(show_id).info, language=language)


@router.get("/tv/shows/{show_id}/external_ids")
async def get_tmdb_show_external_ids(show_id: int) -> dict[str, Any]:
    return await _call_tmdb(TV(show_id).external_ids)


@router.get("/tv/shows/{show_id}/{season_number}")
async def get_tmdb_season(
    season_number: int, show_id: int, language: str = "en"
) -> dict[str, Any]:
    return await _call_tmdb(
        TV_Seasons(season_number=season_number, tv_id=show_id).info,
        language=language,
    )


@router.get("/movies/trending")
async def get_tmdb_trending_movies(
    language: str = "en",
    page: Annotated[int, Query(ge=1, le=500)] = 1,
    time_window: TimeWindow = TimeWindow.DAY,
) -> TmdbPage:
    return await _call_page(
        Trending(media_type="movie", time_window=time_window.value).info,
        language=language,
        page=page,
    )


@router.get("/movies/popular")
async def get_tmdb_popular_movies(
    language: str = "en",
    page: Annotated[int, Query(ge=1, le=500)] = 1,
    region: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
) -> TmdbPage:
    params: dict[str, Any] = {"language": language, "page": page}
    if region:
        params["region"] = region
    return await _call_page(Movies().popular, **params)


@router.get("/movies/upcoming")
async def get_tmdb_upcoming_movies(
    language: str = "en",
    page: Annotated[int, Query(ge=1, le=500)] = 1,
    region: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
) -> TmdbPage:
    params: dict[str, Any] = {"language": language, "page": page}
    if region:
        params["region"] = region
    return await _call_page(Movies().upcoming, **params)


@router.get("/movies/top-rated")
async def get_tmdb_top_rated_movies(
    language: str = "en",
    page: Annotated[int, Query(ge=1, le=500)] = 1,
    region: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
) -> TmdbPage:
    params: dict[str, Any] = {"language": language, "page": page}
    if region:
        params["region"] = region
    return await _call_page(Movies().top_rated, **params)


@router.get("/movies/search")
async def search_tmdb_movies(
    query: Annotated[str, Query(min_length=1, max_length=200)],
    page: Annotated[int, Query(ge=1, le=500)] = 1,
    language: str = "en",
    year: Annotated[int | None, Query(ge=1000, le=9999)] = None,
    include_adult: bool = False,
) -> TmdbPage:
    params: dict[str, Any] = {
        "page": page,
        "query": query,
        "language": language,
        "include_adult": include_adult,
    }
    if year is not None:
        params["primary_release_year"] = year
    return await _call_page(Search().movie, **params)


@router.get("/movies/{movie_id}")
async def get_tmdb_movie(movie_id: int, language: str = "en") -> dict[str, Any]:
    return await _call_tmdb(Movies(movie_id).info, language=language)


@router.get("/movies/{movie_id}/external_ids")
async def get_tmdb_movie_external_ids(movie_id: int) -> dict[str, Any]:
    return await _call_tmdb(Movies(movie_id).external_ids)


@router.get("/discover/{media_type}")
async def discover_tmdb_media(
    media_type: MediaType,
    page: Annotated[int, Query(ge=1, le=500)] = 1,
    language: str = "en",
    region: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    year: Annotated[int | None, Query(ge=1000, le=9999)] = None,
    year_from: Annotated[int | None, Query(ge=1000, le=9999)] = None,
    year_to: Annotated[int | None, Query(ge=1000, le=9999)] = None,
    release_date_from: date | None = None,
    genres: Annotated[str | None, Query(pattern=r"^\d+(,\d+)*$")] = None,
    rating_min: Annotated[float | None, Query(ge=0, le=10)] = None,
    rating_max: Annotated[float | None, Query(ge=0, le=10)] = None,
    sort_by: DiscoverSort = DiscoverSort.POPULARITY_DESC,
    include_adult: bool = False,
) -> TmdbPage:
    if rating_min is not None and rating_max is not None and rating_min > rating_max:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="rating_min must be less than or equal to rating_max.",
        )
    if year_from is not None and year_to is not None and year_from > year_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="year_from must be less than or equal to year_to.",
        )

    params = _discover_params(
        media_type,
        language=language,
        page=page,
        region=region,
        year=year,
        year_from=year_from,
        year_to=year_to,
        release_date_from=release_date_from,
        genres=genres,
        rating_min=rating_min,
        rating_max=rating_max,
        sort_by=sort_by,
        include_adult=include_adult,
    )
    discover = Discover()
    call = discover.movie if media_type is MediaType.MOVIE else discover.tv
    return await _call_page(call, **params)


@router.get("/genres/{media_type}")
async def get_tmdb_genres(
    media_type: MediaType, language: str = "en"
) -> TmdbGenreResponse:
    genres = Genres()
    call = genres.movie_list if media_type is MediaType.MOVIE else genres.tv_list
    payload = await _call_tmdb(call, language=language)
    try:
        return TmdbGenreResponse.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=TMDB_UNAVAILABLE,
        ) from exc
