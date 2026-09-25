# ruff: noqa: S101

import asyncio
from datetime import date

import pytest
from fastapi import HTTPException

from media_manager.release_calendar.router import get_release_calendar


class FakeCalendarRepository:
    async def list_releases(
        self, start_date: date, end_date: date, media_type: str
    ) -> list:
        self.arguments = (start_date, end_date, media_type)
        return []


def test_calendar_rejects_ranges_larger_than_400_days() -> None:
    repository = FakeCalendarRepository()
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            get_release_calendar(
                repository,  # type: ignore[arg-type]
                start_date=date(2026, 1, 1),
                end_date=date(2027, 3, 1),
                media_type="all",
            )
        )
    assert error.value.status_code == 422


def test_calendar_forwards_valid_filters() -> None:
    repository = FakeCalendarRepository()
    result = asyncio.run(
        get_release_calendar(
            repository,  # type: ignore[arg-type]
            start_date=date(2026, 8, 1),
            end_date=date(2026, 9, 1),
            media_type="episode",
        )
    )
    assert result == []
    assert repository.arguments == (
        date(2026, 8, 1),
        date(2026, 9, 1),
        "episode",
    )
