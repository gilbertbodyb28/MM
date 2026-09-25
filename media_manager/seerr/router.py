from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, status

from media_manager.auth.db import User
from media_manager.auth.users import current_active_user
from media_manager.seerr.dependencies import seerr_service_dep
from media_manager.seerr.schemas import (
    SeerrConfiguredStatus,
    SeerrMediaStatus,
    SeerrRequestCreate,
    SeerrRequestResult,
)
from media_manager.seerr.service import SeerrConfigurationError, SeerrProviderError

router = APIRouter()


def _http_error(error: Exception) -> HTTPException:
    status_code = (
        status.HTTP_409_CONFLICT
        if isinstance(error, SeerrConfigurationError)
        else status.HTTP_502_BAD_GATEWAY
    )
    return HTTPException(status_code, str(error))


@router.get("/configured")
def configured(
    service: seerr_service_dep,
    _user: Annotated[User, Depends(current_active_user)],
) -> SeerrConfiguredStatus:
    return service.configured()


@router.get("/status/{media_type}/{tmdb_id}")
async def media_status(
    service: seerr_service_dep,
    _user: Annotated[User, Depends(current_active_user)],
    media_type: Literal["movie", "tv"],
    tmdb_id: Annotated[int, Path(gt=0)],
) -> SeerrMediaStatus:
    try:
        return await service.media_status(media_type, tmdb_id)
    except (SeerrConfigurationError, SeerrProviderError) as error:
        raise _http_error(error) from error


@router.post("/request")
async def create_request(
    payload: SeerrRequestCreate,
    service: seerr_service_dep,
    _user: Annotated[User, Depends(current_active_user)],
) -> SeerrRequestResult:
    try:
        return await service.create_request(payload)
    except (SeerrConfigurationError, SeerrProviderError) as error:
        raise _http_error(error) from error
