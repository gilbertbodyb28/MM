from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from media_manager.auth.users import current_active_user, current_superuser
from media_manager.automation.dependencies import automation_service_dep
from media_manager.automation.schemas import (
    AutomationJob,
    AutomationJobId,
    AutomationJobKind,
    AutomationJobStatus,
)
from media_manager.movies.dependencies import movie_dep
from media_manager.tv.dependencies import show_dep
from media_manager.tv.schemas import EpisodeId, ShowId

router = APIRouter()


@router.get(
    "/jobs",
    dependencies=[Depends(current_active_user)],
)
async def get_automation_jobs(
    automation_service: automation_service_dep,
    job_status: AutomationJobStatus | None = None,
    kind: AutomationJobKind | None = None,
    show_id: ShowId | None = None,
    episode_id: EpisodeId | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AutomationJob]:
    return await automation_service.list_jobs(
        status=job_status,
        kind=kind,
        show_id=show_id,
        episode_id=episode_id,
        limit=limit,
    )


@router.get(
    "/jobs/{job_id}",
    dependencies=[Depends(current_active_user)],
)
async def get_automation_job(
    automation_service: automation_service_dep,
    job_id: AutomationJobId,
) -> AutomationJob:
    return await automation_service.get_job(job_id)


@router.post(
    "/jobs/{job_id}/retry",
    dependencies=[Depends(current_superuser)],
)
async def retry_automation_job(
    automation_service: automation_service_dep,
    job_id: AutomationJobId,
) -> AutomationJob:
    return await automation_service.retry_job(job_id)


@router.post(
    "/movies/{movie_id}",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(current_superuser)],
)
async def queue_movie_download(
    automation_service: automation_service_dep,
    movie: movie_dep,
) -> AutomationJob | None:
    return await automation_service.enqueue_movie(movie, force=True)


@router.post(
    "/shows/{show_id}",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(current_superuser)],
)
async def queue_show_download(
    automation_service: automation_service_dep,
    show: show_dep,
) -> AutomationJob | None:
    return await automation_service.enqueue_show(show, force=True)
