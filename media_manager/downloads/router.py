from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from media_manager.auth.users import current_superuser
from media_manager.downloads.dependencies import qbittorrent_bridge_service_dep
from media_manager.downloads.exceptions import (
    QbittorrentCategoryNotFoundError,
    QbittorrentDisabledError,
    QbittorrentInvalidMagnetError,
    QbittorrentTorrentNotFoundError,
    QbittorrentUnavailableError,
)
from media_manager.downloads.schemas import (
    QbActionResponse,
    QbAddRequest,
    QbAddResponse,
    QbDeleteResponse,
    QbittorrentHash,
    QbSyncResponse,
)

router = APIRouter(dependencies=[Depends(current_superuser)])

TorrentHashPath = Annotated[QbittorrentHash, Path(description="Exact torrent hash")]


def _bridge_http_error(error: Exception) -> HTTPException:
    if isinstance(error, QbittorrentDisabledError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="qBittorrent is not enabled in Settings.",
        )
    if isinstance(error, QbittorrentTorrentNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Torrent was not found in qBittorrent.",
        )
    if isinstance(error, QbittorrentCategoryNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The selected qBittorrent category does not exist.",
        )
    if isinstance(error, QbittorrentInvalidMagnetError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Enter a valid BitTorrent magnet link.",
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="qBittorrent is currently unavailable.",
    )


@router.get("/sync")
async def sync_qbittorrent(
    service: qbittorrent_bridge_service_dep,
    rid: Annotated[int, Query(ge=0, le=2_147_483_647)] = 0,
) -> QbSyncResponse:
    try:
        return await service.sync(rid)
    except (QbittorrentDisabledError, QbittorrentUnavailableError) as error:
        raise _bridge_http_error(error) from error


@router.post("/add", status_code=status.HTTP_202_ACCEPTED)
async def add_qbittorrent_magnet(
    payload: QbAddRequest,
    service: qbittorrent_bridge_service_dep,
) -> QbAddResponse:
    try:
        return await service.add(payload)
    except (
        QbittorrentCategoryNotFoundError,
        QbittorrentDisabledError,
        QbittorrentInvalidMagnetError,
        QbittorrentUnavailableError,
    ) as error:
        raise _bridge_http_error(error) from error


@router.post(
    "/{torrent_hash}/pause",
    status_code=status.HTTP_202_ACCEPTED,
)
async def pause_qbittorrent_torrent(
    torrent_hash: TorrentHashPath,
    service: qbittorrent_bridge_service_dep,
) -> QbActionResponse:
    try:
        await service.pause(torrent_hash)
    except (
        QbittorrentDisabledError,
        QbittorrentTorrentNotFoundError,
        QbittorrentUnavailableError,
    ) as error:
        raise _bridge_http_error(error) from error
    return QbActionResponse(hash=torrent_hash, action="pause")


@router.post(
    "/{torrent_hash}/resume",
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_qbittorrent_torrent(
    torrent_hash: TorrentHashPath,
    service: qbittorrent_bridge_service_dep,
) -> QbActionResponse:
    try:
        await service.resume(torrent_hash)
    except (
        QbittorrentDisabledError,
        QbittorrentTorrentNotFoundError,
        QbittorrentUnavailableError,
    ) as error:
        raise _bridge_http_error(error) from error
    return QbActionResponse(hash=torrent_hash, action="resume")


@router.delete("/{torrent_hash}")
async def delete_qbittorrent_torrent(
    torrent_hash: TorrentHashPath,
    service: qbittorrent_bridge_service_dep,
    delete_files: Annotated[
        bool,
        Query(
            description=(
                "false removes only the qBittorrent job and keeps its payload; "
                "true permanently deletes the payload too"
            )
        ),
    ],
) -> QbDeleteResponse:
    try:
        await service.delete(torrent_hash, delete_files=delete_files)
    except (
        QbittorrentDisabledError,
        QbittorrentTorrentNotFoundError,
        QbittorrentUnavailableError,
    ) as error:
        raise _bridge_http_error(error) from error
    return QbDeleteResponse(hash=torrent_hash, files_deleted=delete_files)
