# ruff: noqa: S101

import asyncio

import httpx

from media_manager.metadataProvider.tmdb_transport import TmdbTransport


def test_direct_tmdb_translates_paths_and_uses_api_key() -> None:
    captured: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(
            200,
            json={"page": 1, "total_pages": 1, "total_results": 0, "results": []},
        )

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            transport = TmdbTransport(client=client, api_key="private-key")
            await transport.get("/movies/search", {"query": "Alien", "page": 1})

    asyncio.run(exercise())
    assert captured is not None
    assert captured.url.path == "/3/search/movie"
    assert captured.url.params["api_key"] == "private-key"


def test_direct_tmdb_uses_bearer_token_without_query_secret() -> None:
    captured: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(200, json={"genres": []})

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            transport = TmdbTransport(
                client=client,
                access_token="private-token",  # noqa: S106
            )
            await transport.get("/genres/tv")

    asyncio.run(exercise())
    assert captured is not None
    assert captured.url.path == "/3/genre/tv/list"
    assert "api_key" not in captured.url.params
    assert captured.headers["authorization"] == "Bearer private-token"


def test_direct_tv_search_translates_year_filter() -> None:
    captured: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(200, json={"results": []})

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            transport = TmdbTransport(client=client, api_key="private-key")
            await transport.get("/tv/search", {"query": "Shogun", "year": 2024})

    asyncio.run(exercise())
    assert captured is not None
    assert captured.url.path == "/3/search/tv"
    assert captured.url.params["first_air_date_year"] == "2024"
    assert "year" not in captured.url.params


def test_direct_discover_parameters_are_translated() -> None:
    captured: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(200, json={"results": []})

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            transport = TmdbTransport(client=client, api_key="private-key")
            await transport.get(
                "/discover/movie",
                {
                    "genres": "12,878",
                    "rating_min": 7.5,
                    "year_from": 2020,
                    "sort_by": "release_date.desc",
                },
            )

    asyncio.run(exercise())
    assert captured is not None
    assert captured.url.params["with_genres"] == "12,878"
    assert captured.url.params["vote_average.gte"] == "7.5"
    assert captured.url.params["primary_release_date.gte"] == "2020-01-01"
    assert captured.url.params["sort_by"] == "primary_release_date.desc"
