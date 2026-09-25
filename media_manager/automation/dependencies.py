from typing import Annotated

from fastapi import Depends

from media_manager.automation.config import AutomationConfig
from media_manager.automation.repository import AutomationRepository
from media_manager.automation.service import AutomationService
from media_manager.config import MediaManagerConfig
from media_manager.database import DbSessionDependency
from media_manager.movies.dependencies import movie_service_dep
from media_manager.torrent.config import TorrentConfig
from media_manager.tv.dependencies import tv_service_dep


def get_automation_repository(db: DbSessionDependency) -> AutomationRepository:
    return AutomationRepository(db)


automation_repository_dep = Annotated[
    AutomationRepository,
    Depends(get_automation_repository),
]


def get_automation_config() -> AutomationConfig:
    application_config = MediaManagerConfig()
    configured = getattr(application_config, "automation", None)
    if isinstance(configured, AutomationConfig):
        return configured
    return AutomationConfig()


automation_config_dep = Annotated[AutomationConfig, Depends(get_automation_config)]


def get_torrent_config() -> TorrentConfig:
    return MediaManagerConfig().torrents


torrent_config_dep = Annotated[TorrentConfig, Depends(get_torrent_config)]


def get_automation_service(
    repository: automation_repository_dep,
    movie_service: movie_service_dep,
    tv_service: tv_service_dep,
    config: automation_config_dep,
    torrent_config: torrent_config_dep,
) -> AutomationService:
    return AutomationService(
        repository=repository,
        movie_service=movie_service,
        tv_service=tv_service,
        config=config,
        torrent_config=torrent_config,
    )


automation_service_dep = Annotated[
    AutomationService,
    Depends(get_automation_service),
]
