from typing import Annotated

from fastapi import Depends

import media_manager.database as database
from media_manager.automation.dependencies import (
    automation_repository_dep,
    torrent_config_dep,
)
from media_manager.config import MediaManagerConfig
from media_manager.database import DbSessionDependency
from media_manager.episode_scanner.config import EpisodeScannerConfig
from media_manager.episode_scanner.repository import EpisodeScanRepository
from media_manager.episode_scanner.schemas import EpisodeScanRunId
from media_manager.episode_scanner.service import (
    EpisodeScanRunner,
    EpisodeScanService,
)
from media_manager.tv.dependencies import tv_service_dep


def get_episode_scan_repository(db: DbSessionDependency) -> EpisodeScanRepository:
    return EpisodeScanRepository(db)


episode_scan_repository_dep = Annotated[
    EpisodeScanRepository,
    Depends(get_episode_scan_repository),
]


def get_episode_scanner_config() -> EpisodeScannerConfig:
    return MediaManagerConfig().episode_scanner


episode_scanner_config_dep = Annotated[
    EpisodeScannerConfig,
    Depends(get_episode_scanner_config),
]


def get_episode_scan_service(
    repository: episode_scan_repository_dep,
    config: episode_scanner_config_dep,
) -> EpisodeScanService:
    return EpisodeScanService(repository=repository, config=config)


episode_scan_service_dep = Annotated[
    EpisodeScanService,
    Depends(get_episode_scan_service),
]


async def renew_episode_scan_lease(run_id: EpisodeScanRunId) -> bool:
    """Renew a scan's lease in its own session; the scan's session may be busy."""
    if database.SessionLocal is None:
        return True
    async with database.SessionLocal() as session:
        return await EpisodeScanRepository(session).touch_run(run_id)


def get_episode_scan_runner(
    repository: episode_scan_repository_dep,
    tv_service: tv_service_dep,
    automation_repository: automation_repository_dep,
    config: episode_scanner_config_dep,
    torrent_config: torrent_config_dep,
) -> EpisodeScanRunner:
    return EpisodeScanRunner(
        repository=repository,
        tv_service=tv_service,
        automation_repository=automation_repository,
        config=config,
        torrent_config=torrent_config,
        lease_keeper=renew_episode_scan_lease,
    )


episode_scan_runner_dep = Annotated[
    EpisodeScanRunner,
    Depends(get_episode_scan_runner),
]
