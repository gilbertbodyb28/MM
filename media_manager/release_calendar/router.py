from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from media_manager.auth.users import current_active_user
from media_manager.release_calendar.dependencies import (
    release_calendar_repository_dep,
)
from media_manager.release_calendar.schemas import ReleaseCalendarItem

router = APIRouter()


@router.get(
    "",
    dependencies=[Depends(current_active_user)],
)
async def get_release_calendar(
    repository: release_calendar_repository_dep,
    start_date: date | None = None,
    end_date: date | None = None,
    media_type: Annotated[
        Literal["all", "movie", "episode"],
        Query(),
    ] = "all",
) -> list[ReleaseCalendarItem]:
    today = datetime.now(tz=UTC).date()
    start = start_date or (today - timedelta(days=30))
    end = end_date or (today + timedelta(days=365))
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="end_date must be on or after start_date",
        )
    if (end - start).days > 400:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Calendar ranges are limited to 400 days",
        )
    return await repository.list_releases(start, end, media_type)
