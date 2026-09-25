# ruff: noqa: S101

import asyncio

import httpx

from media_manager.discover.provider import TmdbDiscoverProvider
from media_manager.discover.schemas import DiscoverSort, MediaType


def test_discover_forwards_typed_filters_to_the_relay() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            json={"page": 2, "total_pages": 4, "total_results": 80, "results": []},
        )

    async def run_test() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TmdbDiscoverProvider(
                client=client,
                relay_url="https://relay.example/tmdb/",
                default_language="sv-SE",
            )
            result = await provider.discover(
                MediaType.MOVIE,
                page=2,
                year=2024,
                year_from=2020,
                year_to=2024,
                genres=[12, 878],
                rating_min=7.5,
                sort_by=DiscoverSort.RATING_DESC,
            )
            assert result.page == 2

    asyncio.run(run_test())

    assert captured_request is not None
    assert captured_request.url.path == "/tmdb/discover/movie"
    assert captured_request.url.params["language"] == "sv-SE"
    assert captured_request.url.params["genres"] == "12,878"
    assert captured_request.url.params["year"] == "2024"
    assert captured_request.url.params["year_from"] == "2020"
    assert captured_request.url.params["year_to"] == "2024"
    assert captured_request.url.params["rating_min"] == "7.5"
    assert captured_request.url.params["sort_by"] == "vote_average.desc"


def test_genres_are_validated() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"genres": [{"id": 28, "name": "Action"}]},
        )

    async def run_test() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TmdbDiscoverProvider(
                client=client,
                relay_url="https://relay.example/tmdb",
                default_language="en",
            )
            genres = await provider.get_genres(MediaType.MOVIE)
            assert [(genre.id, genre.name) for genre in genres] == [(28, "Action")]

    asyncio.run(run_test())
