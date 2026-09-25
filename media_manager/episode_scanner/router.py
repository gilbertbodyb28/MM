import logging

from fastapi import APIRouter, Depends, HTTPException, status

from media_manager.auth.users import current_active_user, current_superuser
from media_manager.episode_scanner.dependencies import episode_scan_service_dep
from media_manager.episode_scanner.schemas import (
    EpisodeScanSettingsUpdate,
    EpisodeScanStatus,
)

router = APIRouter()
log = logging.getLogger(__name__)


@router.get(
    "/status",
    dependencies=[Depends(current_active_user)],
)
async def get_episode_scan_status(
    scan_service: episode_scan_service_dep,
) -> EpisodeScanStatus:
    """Latest scan, next scheduled scan and the episodes that were handled."""
    return await scan_service.get_status()


@router.put(
    "/settings",
    dependencies=[Depends(current_superuser)],
)
async def update_episode_scan_settings(
    payload: EpisodeScanSettingsUpdate,
    scan_service: episode_scan_service_dep,
) -> EpisodeScanStatus:
    """Turn automatic hourly scanning on or off."""
    scan_status = await scan_service.set_enabled(payload.enabled)
    if payload.enabled:
        # Run a due scan right away instead of waiting for the next tick.
        from media_manager.scheduler import schedule_episode_scan_task

        try:
            await schedule_episode_scan_task.kiq()
        except Exception:
            log.exception("Could not wake the episode scanner after enabling it")
    return scan_status


@router.post(
    "/scan",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(current_superuser)],
)
async def start_episode_scan(
    scan_service: episode_scan_service_dep,
) -> EpisodeScanStatus:
    """Start a scan now ("Scanna nu"), whether or not automatic scanning is on."""
    run = await scan_service.start_manual_scan()
    from media_manager.scheduler import run_episode_scan_task

    try:
        await run_episode_scan_task.kiq(run_id=str(run.id))
    except Exception as error:
        log.exception("Could not queue manual episode scan %s", run.id)
        await scan_service.mark_start_failed(run.id, error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scanningen kunde inte startas i bakgrunden.",
        ) from None
    return await scan_service.get_status()
