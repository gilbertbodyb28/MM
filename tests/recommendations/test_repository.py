# ruff: noqa: S101

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from sqlalchemy.sql import Select
from sqlalchemy.sql.dml import Update

from media_manager.recommendations.repository import RecommendationRepository
from media_manager.recommendations.schemas import HistorySource


class EmptyResult:
    def scalar_one_or_none(self) -> None:
        return None


class CapturingSession:
    def __init__(self) -> None:
        self.statement: Select[Any] | None = None

    async def execute(self, statement: Select[Any]) -> EmptyResult:
        self.statement = statement
        return EmptyResult()


def test_plex_account_id_is_authoritative_over_username() -> None:
    session = CapturingSession()
    repository = RecommendationRepository(session)  # type: ignore[arg-type]
    asyncio.run(
        repository.get_mapping_by_plex_identity(
            account_id="authoritative-id",
            username="stale-username",
        )
    )
    assert session.statement is not None
    where_clause = str(session.statement.whereclause)
    assert "plex_account_id" in where_clause
    assert "plex_username" not in where_clause


def test_plex_username_is_used_only_when_account_id_is_absent() -> None:
    session = CapturingSession()
    repository = RecommendationRepository(session)  # type: ignore[arg-type]
    asyncio.run(
        repository.get_mapping_by_plex_identity(
            account_id=None,
            username="legacy-user",
        )
    )
    assert session.statement is not None
    where_clause = str(session.statement.whereclause)
    assert "plex_username" in where_clause
    assert "plex_account_id" not in where_clause


class LeaseSession:
    def __init__(self) -> None:
        self.statements: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, statement: object) -> EmptyResult:
        self.statements.append(statement)
        return EmptyResult()

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def test_database_lease_uses_atomic_expiry_guard_and_reports_occupied() -> None:
    session = LeaseSession()
    repository = RecommendationRepository(session)  # type: ignore[arg-type]
    started_at = datetime.now(UTC)
    acquired = asyncio.run(
        repository.try_acquire_refresh_lease(
            uuid4(),
            HistorySource.TAUTULLI,
            lease_id=uuid4(),
            started_at=started_at,
            expires_at=started_at + timedelta(hours=1),
        )
    )
    assert acquired is False
    assert len(session.statements) == 2
    update_statement = cast(Update, session.statements[1])
    where_clause = str(update_statement.whereclause)
    assert "refresh_lease_expires_at IS NULL" in where_clause
    assert "refresh_lease_expires_at <=" in where_clause
    assert session.commits == 1
    assert session.rollbacks == 0
