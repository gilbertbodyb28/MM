# ruff: noqa: S101

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from media_manager.indexer.repository import IndexerRepository
from media_manager.indexer.schemas import IndexerQueryResult


def make_result(title: str) -> IndexerQueryResult:
    return IndexerQueryResult(
        title=title,
        download_url=f"magnet:?xt=urn:btih:{uuid4().hex}",
        seeders=10,
        flags=[],
        size=1_000_000,
        usenet=False,
        age=0,
        indexer="test",
    )


def test_save_results_adds_every_result_and_commits_once() -> None:
    database = MagicMock()
    database.commit = AsyncMock()
    repository = IndexerRepository(database)
    results = [make_result("One.1080p"), make_result("Two.2160p")]

    saved = asyncio.run(repository.save_results(results))

    assert saved == results
    database.add_all.assert_called_once()
    assert len(database.add_all.call_args.args[0]) == 2
    database.commit.assert_awaited_once()


def test_save_result_remains_a_single_result_compatibility_api() -> None:
    database = MagicMock()
    database.commit = AsyncMock()
    repository = IndexerRepository(database)
    result = make_result("One.1080p")

    saved = asyncio.run(repository.save_result(result))

    assert saved == result
    database.add_all.assert_called_once()
    assert len(database.add_all.call_args.args[0]) == 1
    database.commit.assert_awaited_once()
