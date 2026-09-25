# ruff: noqa: S101

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from media_manager.auth.users import current_active_user
from media_manager.discover.dependencies import get_discover_service
from media_manager.discover.router import router
from media_manager.discover.schemas import DiscoverPage, MediaType


class StubService:
    def __init__(self) -> None:
        self.media_type: MediaType | None = None
        self.query: str | None = None
        self.kwargs: dict[str, Any] = {}

    async def search(
        self, media_type: MediaType, query: str, **kwargs: object
    ) -> DiscoverPage:
        self.media_type = media_type
        self.query = query
        self.kwargs = kwargs
        return DiscoverPage(page=2, total_pages=2, total_results=21, results=[])


def test_search_route_is_authenticated_and_forwards_filters() -> None:
    service = StubService()
    app = FastAPI()
    app.include_router(router, prefix="/discover")
    app.dependency_overrides[current_active_user] = lambda: object()
    app.dependency_overrides[get_discover_service] = lambda: service

    response = TestClient(app).get(
        "/discover/search",
        params=[
            ("query", "foundation"),
            ("media_type", "tv"),
            ("page", "2"),
            ("year", "2021"),
            ("year_from", "2020"),
            ("year_to", "2022"),
            ("genres", "18"),
            ("genres", "10765"),
            ("rating_min", "8"),
        ],
    )

    assert response.status_code == 200
    assert response.json() == {
        "page": 2,
        "total_pages": 2,
        "total_results": 21,
        "results": [],
    }
    assert service.media_type is MediaType.TV
    assert service.query == "foundation"
    assert service.kwargs["genres"] == [18, 10765]
    assert service.kwargs["rating_min"] == 8
    assert service.kwargs["year_from"] == 2020
    assert service.kwargs["year_to"] == 2022


def test_search_route_rejects_invalid_rating() -> None:
    service = StubService()
    app = FastAPI()
    app.include_router(router, prefix="/discover")
    app.dependency_overrides[current_active_user] = lambda: object()
    app.dependency_overrides[get_discover_service] = lambda: service

    response = TestClient(app).get(
        "/discover/search",
        params={"query": "foundation", "rating_min": "11"},
    )

    assert response.status_code == 422
    assert service.query is None
