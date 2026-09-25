# ruff: noqa: S101

import asyncio
from uuid import uuid4

from media_manager.indexer.schemas import IndexerQueryResult
from media_manager.indexer.service import IndexerService


def make_result(title: str, *, size: int = 1_000_000) -> IndexerQueryResult:
    return IndexerQueryResult(
        title=title,
        download_url=f"magnet:?xt=urn:btih:{uuid4().hex}",
        seeders=10,
        flags=[],
        size=size,
        usenet=False,
        age=0,
        indexer="test",
    )


class RecordingRepository:
    def __init__(self) -> None:
        self.saved_batches: list[list[IndexerQueryResult]] = []

    async def save_results(
        self, results: list[IndexerQueryResult]
    ) -> list[IndexerQueryResult]:
        self.saved_batches.append(list(results))
        return results


class OversizedIndexer:
    max_results = 3

    def __init__(self, results: list[IndexerQueryResult]) -> None:
        self.results = results

    def search(self, query: str, is_tv: bool) -> list[IndexerQueryResult]:  # noqa: ARG002
        return self.results


def test_search_caps_deduplicates_and_persists_one_batch() -> None:
    first = make_result("Example.Release.1080p")
    duplicate = make_result("  example.release.1080P  ")
    second = make_result("Another.Release.2160p")
    beyond_limit = make_result("Must.Not.Be.Persisted.720p")
    repository = RecordingRepository()
    service = IndexerService(repository)  # type: ignore[arg-type]
    service.indexers = [  # type: ignore[list-item]
        OversizedIndexer([first, duplicate, second, beyond_limit])
    ]

    results = asyncio.run(service.search("Example", is_tv=False))

    assert results == [first, second]
    assert repository.saved_batches == [[first, second]]


def test_empty_search_still_uses_the_batch_repository_api() -> None:
    repository = RecordingRepository()
    service = IndexerService(repository)  # type: ignore[arg-type]
    service.indexers = []

    results = asyncio.run(service.search("Nothing", is_tv=False))

    assert results == []
    assert repository.saved_batches == [[]]
