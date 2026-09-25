from typing import Annotated

from fastapi import Depends

from media_manager.database import DbSessionDependency
from media_manager.trakt.repository import TraktRepository
from media_manager.trakt.service import TraktService


def get_trakt_repository(db_session: DbSessionDependency) -> TraktRepository:
    return TraktRepository(db_session)


trakt_repository_dep = Annotated[
    TraktRepository,
    Depends(get_trakt_repository),
]


def get_trakt_service(repository: trakt_repository_dep) -> TraktService:
    return TraktService(repository)


trakt_service_dep = Annotated[TraktService, Depends(get_trakt_service)]
