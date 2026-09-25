from datetime import date
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class MediaType(StrEnum):
    MOVIE = "movie"
    TV = "tv"


class TimeWindow(StrEnum):
    DAY = "day"
    WEEK = "week"


class DiscoverCategory(StrEnum):
    DISCOVER = "discover"
    TRENDING = "trending"
    POPULAR = "popular"
    UPCOMING = "upcoming"
    TOP_RATED = "top_rated"


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


class DiscoverGenre(BaseModel):
    id: int = Field(gt=0)
    name: str = Field(min_length=1)


class DiscoverMediaItem(BaseModel):
    external_id: int = Field(gt=0)
    media_type: MediaType
    name: str = Field(min_length=1)
    original_name: str | None = None
    overview: str | None = None
    poster_path: str | None = None
    backdrop_path: str | None = None
    year: int | None = None
    release_date: date | None = None
    vote_average: float | None = Field(default=None, ge=0, le=10)
    vote_count: int = Field(default=0, ge=0)
    popularity: float | None = Field(default=None, ge=0)
    genre_ids: list[int] = Field(default_factory=list)
    original_language: str | None = None
    metadata_provider: Literal["tmdb"] = "tmdb"
    adult: bool = False
    added: bool = False
    id: UUID | None = None


class DiscoverPage(BaseModel):
    page: int = Field(ge=1)
    total_pages: int = Field(ge=0)
    total_results: int = Field(ge=0)
    results: list[DiscoverMediaItem]
