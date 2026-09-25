# ruff: noqa: S101

import asyncio
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from media_manager.discover.provider import RelayPage
from media_manager.discover.schemas import DiscoverCategory, DiscoverSort, MediaType
from media_manager.discover.service import DiscoverService


class StubProvider:
    name = "tmdb"

    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.results = results
        self.search_query: str | None = None

    async def search(
        self, _media_type: MediaType, query: str, **_kwargs: object
    ) -> RelayPage:
        self.search_query = query
        return RelayPage(
            page=1,
            total_pages=3,
            total_results=60,
            results=self.results,
        )


class StubResult:
    def __init__(self, rows: list[tuple[int, UUID]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[int, UUID]]:
        return self.rows


class StubSession:
    def __init__(self, rows: list[tuple[int, UUID]]) -> None:
        self.rows = rows
        self.execute_count = 0

    async def execute(self, _statement: object) -> StubResult:
        self.execute_count += 1
        return StubResult(self.rows)


def test_search_formats_filters_and_sorts_results() -> None:
    provider = StubProvider(
        [
            {
                "id": 10,
                "title": "Lower rated",
                "release_date": "2024-01-01",
                "poster_path": "/poster.jpg",
                "genre_ids": [12, 878],
                "vote_average": 7.4,
                "vote_count": 100,
                "popularity": 50,
            },
            {
                "id": 20,
                "title": "Best match",
                "release_date": "2024-05-01",
                "poster_path": None,
                "genre_ids": [12, 878],
                "vote_average": 8.8,
                "vote_count": 250,
                "popularity": 40,
            },
            {
                "id": 30,
                "title": "Wrong genre",
                "release_date": "2024-03-01",
                "genre_ids": [35],
                "vote_average": 9.2,
            },
        ]
    )
    service = DiscoverService(provider=provider, db_session=None)  # type: ignore[arg-type]

    result = asyncio.run(
        service.search(
            MediaType.MOVIE,
            "  space  ",
            year_from=2023,
            year_to=2024,
            genres=[12, 878],
            rating_min=7,
            sort_by=DiscoverSort.RATING_DESC,
        )
    )

    assert provider.search_query == "space"
    assert [item.external_id for item in result.results] == [20, 10]
    assert result.results[1].poster_path == "https://image.tmdb.org/t/p/w500/poster.jpg"
    assert result.total_results == 60


def test_invalid_rating_range_is_rejected_before_calling_provider() -> None:
    provider = StubProvider([])
    service = DiscoverService(provider=provider, db_session=None)  # type: ignore[arg-type]

    with pytest.raises(HTTPException) as exception_info:
        asyncio.run(
            service.search(
                MediaType.TV,
                "query",
                rating_min=8,
                rating_max=4,
            )
        )

    assert exception_info.value.status_code == 422
    assert provider.search_query is None


def test_invalid_year_range_is_rejected_before_calling_provider() -> None:
    provider = StubProvider([])
    service = DiscoverService(provider=provider, db_session=None)  # type: ignore[arg-type]

    with pytest.raises(HTTPException) as exception_info:
        asyncio.run(
            service.search(
                MediaType.TV,
                "query",
                year_from=2024,
                year_to=2020,
            )
        )

    assert exception_info.value.status_code == 422
    assert provider.search_query is None


def test_trending_rejects_filters_instead_of_changing_dataset() -> None:
    provider = StubProvider([])
    service = DiscoverService(provider=provider, db_session=None)  # type: ignore[arg-type]

    with pytest.raises(HTTPException) as exception_info:
        asyncio.run(
            service.discover(
                MediaType.MOVIE,
                category=DiscoverCategory.TRENDING,
                year_from=2020,
            )
        )

    assert exception_info.value.status_code == 422
    assert "trending" in str(exception_info.value.detail).lower()


def test_malformed_provider_results_are_ignored() -> None:
    provider = StubProvider(
        [
            {"id": None, "name": "Missing id"},
            {"id": 12, "name": "Valid show", "first_air_date": "not-a-date"},
        ]
    )
    service = DiscoverService(provider=provider, db_session=None)  # type: ignore[arg-type]

    result = asyncio.run(service.search(MediaType.TV, "show"))

    assert len(result.results) == 1
    assert result.results[0].external_id == 12
    assert result.results[0].year is None


def test_library_items_are_enriched_in_one_database_query() -> None:
    internal_id = uuid4()
    provider = StubProvider(
        [
            {"id": 10, "title": "In library", "release_date": "2020-01-01"},
            {"id": 20, "title": "Not added", "release_date": "2021-01-01"},
        ]
    )
    session = StubSession([(10, internal_id)])
    service = DiscoverService(
        provider=provider,  # type: ignore[arg-type]
        db_session=cast(AsyncSession, session),
    )

    result = asyncio.run(service.search(MediaType.MOVIE, "library"))

    assert session.execute_count == 1
    assert result.results[0].added is True
    assert result.results[0].id == internal_id
    assert result.results[1].added is False
    assert result.results[1].id is None
