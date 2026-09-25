from typing import Annotated, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from media_manager.auth.db import User
from media_manager.auth.users import current_active_user, current_superuser
from media_manager.automation.dependencies import automation_service_dep
from media_manager.exceptions import ConflictError, NotFoundError
from media_manager.metadataProvider.dependencies import metadata_provider_dep
from media_manager.movies.dependencies import movie_metadata_service_dep
from media_manager.trakt.dependencies import trakt_service_dep
from media_manager.trakt.schemas import (
    TraktAuthorizeResponse,
    TraktImportRequest,
    TraktImportResult,
    TraktImportResultItem,
    TraktItemCollection,
    TraktStatus,
)
from media_manager.trakt.service import (
    TraktAuthenticationError,
    TraktConfigurationError,
    TraktProviderError,
    TraktSource,
)
from media_manager.tv.dependencies import tv_metadata_service_dep, tv_service_dep
from media_manager.tv.schemas import MonitorScope

router = APIRouter()


def _upstream_error(error: Exception) -> HTTPException:
    if isinstance(error, TraktConfigurationError):
        return HTTPException(status.HTTP_409_CONFLICT, str(error))
    if isinstance(error, TraktAuthenticationError):
        return HTTPException(status.HTTP_401_UNAUTHORIZED, str(error))
    return HTTPException(status.HTTP_502_BAD_GATEWAY, str(error))


@router.get("/status")
async def get_status(
    service: trakt_service_dep,
    user: Annotated[User, Depends(current_active_user)],
) -> TraktStatus:
    return await service.status(user.id)


@router.get("/authorize")
def authorize(
    service: trakt_service_dep,
    user: Annotated[User, Depends(current_active_user)],
) -> TraktAuthorizeResponse:
    try:
        return service.authorization_url(user.id)
    except TraktConfigurationError as error:
        raise _upstream_error(error) from error


@router.get("/callback")
async def callback(
    service: trakt_service_dep,
    user: Annotated[User, Depends(current_active_user)],
    code: Annotated[str, Query(min_length=1, max_length=2_000)],
    state: Annotated[str, Query(min_length=1, max_length=4_000)],
) -> RedirectResponse:
    try:
        await service.connect(user.id, code=code, state=state)
        outcome = {"trakt": "connected"}
    except (TraktConfigurationError, TraktAuthenticationError, TraktProviderError):
        outcome = {"trakt": "error"}
    separator = "&" if "?" in str(service.config.frontend_return_url) else "?"
    return RedirectResponse(
        f"{service.config.frontend_return_url}{separator}{urlencode(outcome)}"
    )


@router.delete("/connection", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(
    service: trakt_service_dep,
    user: Annotated[User, Depends(current_active_user)],
) -> None:
    await service.disconnect(user.id)


@router.get("/items")
async def list_items(
    service: trakt_service_dep,
    user: Annotated[User, Depends(current_active_user)],
    source: TraktSource = "watchlist",
    media_type: Literal["all", "movie", "show"] = "all",
) -> TraktItemCollection:
    try:
        return await service.list_items(
            user.id,
            source=source,
            media_type=media_type,
        )
    except (
        TraktConfigurationError,
        TraktAuthenticationError,
        TraktProviderError,
    ) as error:
        raise _upstream_error(error) from error


@router.post("/import", dependencies=[Depends(current_superuser)])
async def import_selected(
    payload: TraktImportRequest,
    movie_metadata_service: movie_metadata_service_dep,
    tv_metadata_service: tv_metadata_service_dep,
    tv_service: tv_service_dep,
    metadata_provider: metadata_provider_dep,
    automation_service: automation_service_dep,
) -> TraktImportResult:
    results: list[TraktImportResultItem] = []
    for item in payload.items:
        try:
            already_added = False
            if item.media_type == "movie":
                already_added = await movie_metadata_service.check_if_exists(
                    item.tmdb_id,
                    metadata_provider.name,
                )
                if already_added:
                    media = await movie_metadata_service.movie_repository.get_movie_by_external_id(
                        item.tmdb_id,
                        metadata_provider.name,
                    )
                else:
                    media = await movie_metadata_service.add_movie(
                        item.tmdb_id,
                        metadata_provider,
                    )
                await automation_service.enqueue_movie(media)
            else:
                already_added = await tv_metadata_service.check_if_exists(
                    item.tmdb_id,
                    metadata_provider.name,
                )
                if already_added:
                    media = (
                        await tv_metadata_service.tv_repository.get_show_by_external_id(
                            item.tmdb_id,
                            metadata_provider.name,
                        )
                    )
                else:
                    media = await tv_metadata_service.add_show(
                        item.tmdb_id,
                        metadata_provider,
                    )
                media = await tv_service.configure_show_monitoring(
                    media,
                    monitored=False,
                    monitor_scope=MonitorScope.ENTIRE,
                    monitored_season_numbers=set(),
                )
                await automation_service.enqueue_show(media)
            results.append(
                TraktImportResultItem(
                    media_type=item.media_type,
                    tmdb_id=item.tmdb_id,
                    title=item.title,
                    success=True,
                    already_added=already_added,
                    media_id=media.id,
                )
            )
        except (ConflictError, NotFoundError, ValueError) as error:
            results.append(
                TraktImportResultItem(
                    media_type=item.media_type,
                    tmdb_id=item.tmdb_id,
                    title=item.title,
                    success=False,
                    error=str(error)[:300] or "Media metadata could not be imported.",
                )
            )
        except Exception:
            results.append(
                TraktImportResultItem(
                    media_type=item.media_type,
                    tmdb_id=item.tmdb_id,
                    title=item.title,
                    success=False,
                    error="MediaManager could not import this title.",
                )
            )
    return TraktImportResult(
        imported=sum(item.success and not item.already_added for item in results),
        failed=sum(not item.success for item in results),
        results=results,
    )
