# ruff: noqa: S101

import asyncio
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from media_manager.tv.metadata import TvMetadataService
from media_manager.tv.repository import TvRepository
from media_manager.tv.schemas import Show


class UnusedSession:
    """The eager query is stubbed; a database call would be a regression."""

    async def execute(self, _statement: object) -> None:
        message = "The generic lazy-loading query must not run"
        raise AssertionError(message)


def test_recommended_show_existence_check_uses_eager_show_query() -> None:
    repository = TvRepository(cast(AsyncSession, UnusedSession()))
    calls: list[tuple[int, str]] = []
    expected = object()

    async def get_show_by_external_id(
        external_id: int,
        metadata_provider: str,
    ) -> Show:
        calls.append((external_id, metadata_provider))
        return cast(Show, expected)

    repository.get_show_by_external_id = get_show_by_external_id  # type: ignore[method-assign]
    service = TvMetadataService(repository)

    exists = asyncio.run(service.check_if_exists(65942, "tmdb"))

    assert exists is True
    assert calls == [(65942, "tmdb")]
