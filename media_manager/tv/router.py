import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from media_manager.auth.users import current_active_user, current_superuser
from media_manager.automation.dependencies import automation_service_dep
from media_manager.automation.schemas import AutomationJob
from media_manager.config import LibraryItem, MediaManagerConfig
from media_manager.indexer.schemas import (
    IndexerQueryResult,
    IndexerQueryResultId,
)
from media_manager.metadataProvider.dependencies import metadata_provider_dep
from media_manager.metadataProvider.schemas import MetaDataProviderSearchResult
from media_manager.schemas import MediaImportSuggestion
from media_manager.torrent.schemas import Torrent
from media_manager.torrent.utils import get_importable_media_directories
from media_manager.tv.dependencies import (
    season_dep,
    show_dep,
    tv_import_service_dep,
    tv_metadata_service_dep,
    tv_service_dep,
)
from media_manager.tv.schemas import (
    EpisodeId,
    MonitoringMode,
    MonitorScope,
    PublicEpisodeFile,
    PublicShow,
    RichShowTorrent,
    Season,
    Show,
    ShowId,
)

router = APIRouter()
log = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# METADATA & SEARCH
# -----------------------------------------------------------------------------


@router.get(
    "/search",
    dependencies=[Depends(current_active_user)],
)
async def search_metadata_providers_for_a_show(
    tv_metadata_service: tv_metadata_service_dep,
    query: str,
    metadata_provider: metadata_provider_dep,
) -> list[MetaDataProviderSearchResult]:
    """
    Search for a show on the configured metadata provider.
    """
    return await tv_metadata_service.search_for_show(
        query=query, metadata_provider=metadata_provider
    )


@router.get(
    "/recommended",
    dependencies=[Depends(current_active_user)],
)
async def get_recommended_shows(
    tv_metadata_service: tv_metadata_service_dep,
    metadata_provider: metadata_provider_dep,
) -> list[MetaDataProviderSearchResult]:
    """
    Get a list of recommended/popular shows from the metadata provider.
    """
    return await tv_metadata_service.get_popular_shows(
        metadata_provider=metadata_provider
    )


# -----------------------------------------------------------------------------
# IMPORTING
# -----------------------------------------------------------------------------


@router.get(
    "/importable",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(current_superuser)],
)
async def get_all_importable_shows(
    tv_import_service: tv_import_service_dep, metadata_provider: metadata_provider_dep
) -> list[MediaImportSuggestion]:
    """
    Get a list of unknown shows that were detected in the TV directory and are importable.
    """
    return await tv_import_service.get_importable_tv_shows(
        metadata_provider=metadata_provider
    )


@router.post(
    "/importable/{show_id}",
    dependencies=[Depends(current_superuser)],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def import_detected_show(
    tv_import_service: tv_import_service_dep, tv_show: show_dep, directory: str
) -> None:
    """
    Import a detected show from the specified directory into the library.
    """
    source_directory = Path(directory)
    if source_directory not in get_importable_media_directories(
        MediaManagerConfig().misc.tv_directory
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No such directory")
    await tv_import_service.import_existing_tv_show(
        tv_show=tv_show, source_directory=source_directory
    )


# -----------------------------------------------------------------------------
# SHOWS
# -----------------------------------------------------------------------------


@router.get(
    "/shows",
    dependencies=[Depends(current_active_user)],
)
async def get_all_shows(tv_service: tv_service_dep) -> list[Show]:
    """
    Get all shows in the library.
    """
    return await tv_service.get_all_shows()


@router.post(
    "/shows",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(current_superuser)],
    responses={
        status.HTTP_200_OK: {
            "model": Show,
            "description": "Show already existed; monitoring settings were updated",
        },
        status.HTTP_201_CREATED: {
            "model": Show,
            "description": "Successfully created show",
        },
    },
)
async def add_a_show(
    tv_metadata_service: tv_metadata_service_dep,
    tv_service: tv_service_dep,
    metadata_provider: metadata_provider_dep,
    automation_service: automation_service_dep,
    response: Response,
    show_id: int,
    language: str | None = None,
    monitoring: MonitoringMode = MonitoringMode.UNMONITORED,
    monitor_scope: MonitorScope = MonitorScope.ENTIRE,
    monitor_season: Annotated[list[int] | None, Query()] = None,
) -> Show:
    """
    Add a new show to the library and, when enabled, queue its automatic
    download. This operation is restricted to administrators because it can
    allocate network, disk, and download-client resources.
    """
    selected_seasons = set(monitor_season or [])
    is_monitored = monitoring == MonitoringMode.MONITORED
    if is_monitored and monitor_scope == MonitorScope.SPECIFIC and not selected_seasons:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select at least one season when monitoring specific seasons.",
        )

    already_exists = await tv_metadata_service.check_if_exists(
        external_id=show_id,
        metadata_provider=metadata_provider.name,
    )
    if already_exists:
        show = await tv_metadata_service.tv_repository.get_show_by_external_id(
            show_id,
            metadata_provider=metadata_provider.name,
        )
    else:
        show = await tv_metadata_service.add_show(
            external_id=show_id,
            metadata_provider=metadata_provider,
            language=language,
        )

    try:
        show = await tv_service.configure_show_monitoring(
            show,
            monitored=is_monitored,
            monitor_scope=monitor_scope if is_monitored else MonitorScope.ENTIRE,
            monitored_season_numbers=selected_seasons,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    job = await automation_service.enqueue_show(show)
    if job is not None:
        from media_manager.scheduler import run_download_automation_task

        await run_download_automation_task.kiq()
    response.status_code = (
        status.HTTP_200_OK if already_exists else status.HTTP_201_CREATED
    )
    log.info(
        "[MediaAdd] TV show %s: %s",
        show.id,
        "already existed" if already_exists else "created successfully",
    )
    return show


@router.get(
    "/shows/preview",
    dependencies=[Depends(current_superuser)],
)
async def preview_a_show(
    tv_metadata_service: tv_metadata_service_dep,
    metadata_provider: metadata_provider_dep,
    show_id: int,
    language: str | None = None,
) -> Show:
    """Fetch season choices without persisting the show."""
    return await tv_metadata_service.preview_show(
        external_id=show_id,
        metadata_provider=metadata_provider,
        language=language,
    )


@router.get(
    "/shows/torrents",
    dependencies=[Depends(current_active_user)],
)
async def get_shows_with_torrents(tv_service: tv_service_dep) -> list[RichShowTorrent]:
    """
    Get all shows that are associated with torrents.
    """
    return await tv_service.get_all_shows_with_torrents()


@router.get(
    "/shows/libraries",
    dependencies=[Depends(current_active_user)],
)
def get_available_libraries() -> list[LibraryItem]:
    """
    Get available TV libraries from configuration.
    """
    return MediaManagerConfig().misc.tv_libraries


# -----------------------------------------------------------------------------
# SHOWS - INDIVIDUAL
# -----------------------------------------------------------------------------


@router.get(
    "/shows/{show_id}",
    dependencies=[Depends(current_active_user)],
)
async def get_a_show(show: show_dep, tv_service: tv_service_dep) -> PublicShow:
    """
    Get details for a specific show.
    """
    return await tv_service.get_public_show_by_id(show=show)


@router.delete(
    "/shows/{show_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(current_superuser)],
)
async def delete_a_show(
    tv_service: tv_service_dep,
    show: show_dep,
    delete_files_on_disk: bool = False,
    delete_torrents: bool = False,
) -> None:
    """
    Delete a show from the library.
    """
    await tv_service.delete_show(
        show=show,
        delete_files_on_disk=delete_files_on_disk,
        delete_torrents=delete_torrents,
    )


@router.post(
    "/shows/{show_id}/metadata",
    dependencies=[Depends(current_active_user)],
)
async def update_shows_metadata(
    show: show_dep,
    tv_metadata_service: tv_metadata_service_dep,
    tv_service: tv_service_dep,
    metadata_provider: metadata_provider_dep,
) -> PublicShow:
    """
    Update a show's metadata from the provider.
    """
    await tv_metadata_service.update_show_metadata(
        db_show=show, metadata_provider=metadata_provider
    )
    return await tv_service.get_public_show_by_id(show=show)


@router.post(
    "/shows/{show_id}/continuousDownload",
    dependencies=[Depends(current_superuser)],
)
async def set_continuous_download(
    show: show_dep,
    tv_service: tv_service_dep,
    automation_service: automation_service_dep,
    continuous_download: bool,
) -> PublicShow:
    """
    Toggle whether future seasons of a show will be automatically downloaded.
    """
    updated_show = await tv_service.set_show_continuous_download(
        show=show, continuous_download=continuous_download
    )
    if continuous_download:
        job = await automation_service.enqueue_show(updated_show)
        if job is not None:
            # Publish an immediate wake-up after the persisted monitor flag and
            # automation job have committed. The five-minute schedule remains a
            # recovery net if the worker is temporarily unavailable.
            from media_manager.scheduler import run_download_automation_task

            await run_download_automation_task.kiq()
    return await tv_service.get_public_show_by_id(show=updated_show)


@router.post(
    "/shows/{show_id}/library",
    dependencies=[Depends(current_superuser)],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def set_library(
    show: show_dep,
    tv_service: tv_service_dep,
    library: str,
) -> None:
    """
    Set the library path for a Show.
    """
    await tv_service.set_show_library(show=show, library=library)
    return


@router.get(
    "/shows/{show_id}/torrents",
    dependencies=[Depends(current_active_user)],
)
async def get_a_shows_torrents(
    show: show_dep, tv_service: tv_service_dep
) -> RichShowTorrent:
    """
    Get torrents associated with a specific show.
    """
    return await tv_service.get_torrents_for_show(show=show)


# -----------------------------------------------------------------------------
# EPISODE SEARCHES
# -----------------------------------------------------------------------------


@router.get(
    "/shows/{show_id}/episodes/{episode_id}/releases",
    dependencies=[Depends(current_superuser)],
)
async def search_releases_for_an_episode(
    show: show_dep,
    episode_id: EpisodeId,
    tv_service: tv_service_dep,
) -> list[IndexerQueryResult]:
    """Run an interactive Prowlarr search for one exact episode."""
    return await tv_service.get_episode_releases(
        show=show,
        episode_id=episode_id,
    )


@router.post(
    "/shows/{show_id}/episodes/{episode_id}/releases/{result_id}/grab",
    dependencies=[Depends(current_superuser)],
)
async def grab_release_for_an_episode(
    show: show_dep,
    episode_id: EpisodeId,
    result_id: IndexerQueryResultId,
    tv_service: tv_service_dep,
) -> Torrent:
    """Validate and send an interactively selected release to the client."""
    return await tv_service.download_episode_release(
        show=show,
        episode_id=episode_id,
        result_id=result_id,
    )


@router.post(
    "/shows/{show_id}/episodes/{episode_id}/automatic-search",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(current_superuser)],
)
async def automatically_search_for_an_episode(
    show: show_dep,
    episode_id: EpisodeId,
    automation_service: automation_service_dep,
) -> AutomationJob:
    """Queue a durable exact-episode search and wake the background worker."""
    job = await automation_service.enqueue_episode(
        show,
        episode_id,
        force=True,
    )
    from media_manager.scheduler import run_download_automation_task

    await run_download_automation_task.kiq()
    return job


# -----------------------------------------------------------------------------
# SEASONS
# -----------------------------------------------------------------------------


@router.get(
    "/seasons/{season_id}",
    dependencies=[Depends(current_active_user)],
)
async def get_season(season: season_dep) -> Season:
    """
    Get details for a specific season.
    """
    return season


@router.get(
    "/seasons/{season_id}/files",
    dependencies=[Depends(current_active_user)],
)
async def get_episode_files(
    season: season_dep, tv_service: tv_service_dep
) -> list[PublicEpisodeFile]:
    """
    Get episode files associated with a specific season.
    """
    return await tv_service.get_public_episode_files_by_season_id(season=season)


# -----------------------------------------------------------------------------
# TORRENTS
# -----------------------------------------------------------------------------


@router.get(
    "/torrents",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(current_superuser)],
)
async def get_torrents_for_a_season(
    tv_service: tv_service_dep,
    show_id: ShowId,
    season_number: int = 1,
    search_query_override: str | None = None,
) -> list[IndexerQueryResult]:
    """
    Search for torrents for a specific season of a show.
    Default season_number is 1 because it often returns multi-season torrents.
    """
    return await tv_service.get_all_available_torrents_for_a_season(
        season_number=season_number,
        show_id=show_id,
        search_query_override=search_query_override,
    )


@router.post(
    "/torrents",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(current_superuser)],
)
async def download_a_torrent(
    tv_service: tv_service_dep,
    public_indexer_result_id: IndexerQueryResultId,
    show_id: ShowId,
    override_file_path_suffix: str = "",
) -> Torrent:
    """
    Trigger a download for a specific torrent.
    """
    return await tv_service.download_torrent(
        public_indexer_result_id=public_indexer_result_id,
        show_id=show_id,
        override_show_file_path_suffix=override_file_path_suffix,
    )


# -----------------------------------------------------------------------------
# STATISTICS
# -----------------------------------------------------------------------------


@router.get(
    "/episodes/count",
    status_code=status.HTTP_200_OK,
    description="Total number of episodes downloaded",
    dependencies=[Depends(current_active_user)],
)
async def get_total_count_of_downloaded_episodes(tv_service: tv_service_dep) -> int:
    """
    Get the total count of downloaded episodes across all shows.
    """
    return await tv_service.get_total_downloaded_episodes_count()
