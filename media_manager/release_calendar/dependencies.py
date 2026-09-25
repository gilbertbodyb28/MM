from typing import Annotated

from fastapi import Depends

from media_manager.database import DbSessionDependency
from media_manager.release_calendar.repository import ReleaseCalendarRepository


def get_release_calendar_repository(
    db: DbSessionDependency,
) -> ReleaseCalendarRepository:
    return ReleaseCalendarRepository(db)


release_calendar_repository_dep = Annotated[
    ReleaseCalendarRepository,
    Depends(get_release_calendar_repository),
]
