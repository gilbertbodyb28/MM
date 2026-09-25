import asyncio
from collections.abc import Mapping
from typing import Any

from media_manager.downloads.exceptions import (
    QbittorrentDisabledError,
    QbittorrentInvalidMagnetError,
)
from media_manager.downloads.qbittorrent import QbittorrentGateway
from media_manager.downloads.schemas import (
    QbAddRequest,
    QbAddResponse,
    QbServerState,
    QbSyncResponse,
    QbTorrent,
    validate_magnet_uri,
    validate_qbittorrent_hash,
)
from media_manager.torrent.config import QbittorrentConfig

INFINITE_ETA_SECONDS = 8_640_000


def _integer(value: object, *, minimum: int = 0) -> int:
    if not isinstance(value, str | bytes | bytearray | int | float):
        return minimum
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return minimum
    return max(parsed, minimum)


def _number(value: object, *, minimum: float = 0) -> float:
    if not isinstance(value, str | bytes | bytearray | int | float):
        return minimum
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return minimum
    return max(parsed, minimum)


def _timestamp(value: object) -> int | None:
    timestamp = _integer(value)
    return timestamp or None


def _torrent_from_raw(torrent_hash: str, raw: Mapping[str, Any]) -> QbTorrent:
    eta_value = _integer(raw.get("eta"))
    eta = None if eta_value >= INFINITE_ETA_SECONDS else eta_value
    return QbTorrent(
        hash=torrent_hash,
        name=str(raw.get("name") or "")[:1024],
        state=str(raw.get("state") or "unknown")[:64],
        progress=min(_number(raw.get("progress")), 1),
        download_speed=_integer(raw.get("dlspeed")),
        upload_speed=_integer(raw.get("upspeed")),
        eta=eta,
        size=_integer(raw.get("size")),
        downloaded=_integer(raw.get("downloaded")),
        uploaded=_integer(raw.get("uploaded")),
        amount_left=_integer(raw.get("amount_left")),
        ratio=_number(raw.get("ratio")),
        seeds=_integer(raw.get("num_seeds")),
        peers=_integer(raw.get("num_leechs")),
        category=str(raw.get("category") or "")[:200],
        added_on=_timestamp(raw.get("added_on")),
        completion_on=_timestamp(raw.get("completion_on")),
    )


def _server_state_from_raw(raw: Mapping[str, Any]) -> QbServerState:
    return QbServerState(
        connection_status=str(raw.get("connection_status") or "unknown")[:64],
        download_speed=_integer(raw.get("dl_info_speed")),
        upload_speed=_integer(raw.get("up_info_speed")),
        total_downloaded=_integer(raw.get("alltime_dl")),
        total_uploaded=_integer(raw.get("alltime_ul")),
        free_space=_integer(raw.get("free_space_on_disk")),
    )


class QbittorrentBridgeService:
    def __init__(
        self,
        config: QbittorrentConfig,
        gateway: QbittorrentGateway | None = None,
    ) -> None:
        self.config = config
        self.gateway = gateway or QbittorrentGateway(config)

    def _require_enabled(self) -> None:
        if not self.config.enabled:
            raise QbittorrentDisabledError

    async def sync(self, rid: int) -> QbSyncResponse:
        self._require_enabled()
        delta, snapshot = await asyncio.to_thread(self.gateway.sync, rid)
        raw_snapshot_torrents = snapshot.get("torrents", {})
        snapshot_torrents = (
            raw_snapshot_torrents if isinstance(raw_snapshot_torrents, Mapping) else {}
        )
        delta_torrents = delta.get("torrents", {})
        changed_hashes = (
            set(snapshot_torrents)
            if bool(delta.get("full_update")) or rid == 0
            else set(delta_torrents)
            if isinstance(delta_torrents, Mapping)
            else set()
        )
        torrents: dict[str, QbTorrent] = {}
        for torrent_hash in changed_hashes:
            raw = snapshot_torrents.get(torrent_hash)
            if not isinstance(torrent_hash, str) or not isinstance(raw, Mapping):
                continue
            try:
                torrent = _torrent_from_raw(torrent_hash, raw)
            except ValueError:
                continue
            torrents[torrent.hash] = torrent

        removed: list[str] = []
        raw_removed = delta.get("torrents_removed", [])
        if isinstance(raw_removed, list):
            for torrent_hash in raw_removed:
                if not isinstance(torrent_hash, str):
                    continue
                try:
                    removed.append(validate_qbittorrent_hash(torrent_hash))
                except (TypeError, ValueError):
                    continue

        raw_categories = snapshot.get("categories", {})
        category_names = (
            sorted(str(name)[:200] for name in raw_categories)
            if isinstance(raw_categories, Mapping)
            else []
        )
        raw_server_state = snapshot.get("server_state", {})
        server_state = _server_state_from_raw(
            raw_server_state if isinstance(raw_server_state, Mapping) else {}
        )
        return QbSyncResponse(
            rid=_integer(delta.get("rid")),
            full_update=bool(delta.get("full_update")) or rid == 0,
            torrents=torrents,
            removed=removed,
            categories=category_names,
            server_state=server_state,
        )

    async def pause(self, torrent_hash: str) -> None:
        self._require_enabled()
        await asyncio.to_thread(self.gateway.pause, torrent_hash)

    async def resume(self, torrent_hash: str) -> None:
        self._require_enabled()
        await asyncio.to_thread(self.gateway.resume, torrent_hash)

    async def delete(self, torrent_hash: str, *, delete_files: bool) -> None:
        self._require_enabled()
        await asyncio.to_thread(
            self.gateway.delete,
            torrent_hash,
            delete_files=delete_files,
        )

    async def add(self, payload: QbAddRequest) -> QbAddResponse:
        self._require_enabled()
        try:
            magnet_uri = validate_magnet_uri(payload.magnet_uri)
        except ValueError:
            raise QbittorrentInvalidMagnetError from None
        category = await asyncio.to_thread(
            self.gateway.add_magnet,
            magnet_uri,
            payload.category,
        )
        return QbAddResponse(category=category)
