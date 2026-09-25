# ruff: noqa: S101

import asyncio
import json
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from media_manager.downloads.exceptions import (
    QbittorrentDisabledError,
    QbittorrentInvalidMagnetError,
)
from media_manager.downloads.schemas import QbAddRequest, validate_qbittorrent_hash
from media_manager.downloads.service import QbittorrentBridgeService
from media_manager.torrent.config import QbittorrentConfig

TORRENT_HASH = "A" * 40


def raw_torrent(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Example.Show.S01E01",
        "state": "downloading",
        "progress": 0.42125,
        "dlspeed": 1_250_000,
        "upspeed": 25_000,
        "eta": 123,
        "size": 5_000_000,
        "downloaded": 2_100_000,
        "uploaded": 10_000,
        "amount_left": 2_900_000,
        "ratio": 0.04,
        "num_seeds": 12,
        "num_leechs": 3,
        "category": "MediaManager",
        "added_on": 1_700_000_000,
        "completion_on": 0,
        "magnet_uri": "magnet:?xt=urn:btih:secret",
        "tracker": "https://tracker.invalid/private-passkey",
        "comment": "private comment",
        "save_path": "/private/download/path",
        "content_path": "/private/download/path/file.mkv",
    }
    payload.update(overrides)
    return payload


def sync_payload(
    *,
    torrent: dict[str, object] | None = None,
    full_update: bool = True,
) -> dict[str, object]:
    return {
        "rid": 7,
        "full_update": full_update,
        "torrents": {TORRENT_HASH: torrent or raw_torrent()},
        "categories": {
            "MediaManager": {"savePath": "/private/download/path"},
            "tv": {"savePath": "/another/private/path"},
        },
        "server_state": {
            "connection_status": "connected",
            "dl_info_speed": 1_250_000,
            "up_info_speed": 25_000,
            "alltime_dl": 9_000_000,
            "alltime_ul": 3_000_000,
            "free_space_on_disk": 50_000_000,
        },
    }


def enabled_service(gateway: Mock) -> QbittorrentBridgeService:
    return QbittorrentBridgeService(
        QbittorrentConfig(enabled=True, category_name="MediaManager"),
        gateway=gateway,
    )


def test_full_sync_is_hydrated_and_sanitized() -> None:
    gateway = Mock()
    payload = sync_payload(torrent=raw_torrent(eta=8_640_000))
    gateway.sync.return_value = (payload, payload)

    result = asyncio.run(enabled_service(gateway).sync(0))

    torrent = result.torrents[TORRENT_HASH.lower()]
    assert torrent.name == "Example.Show.S01E01"
    assert torrent.progress == 0.42125
    assert torrent.eta is None
    assert torrent.completion_on is None
    assert result.categories == ["MediaManager", "tv"]
    assert result.server_state.download_speed == 1_250_000
    serialized = json.dumps(result.model_dump())
    assert "private-passkey" not in serialized
    assert "/private/download/path" not in serialized
    assert "magnet_uri" not in serialized
    assert "tracker" not in serialized


def test_incremental_qbittorrent_patch_is_returned_as_full_torrent() -> None:
    delta = {
        "rid": 8,
        "torrents": {TORRENT_HASH: {"progress": 0.5}},
        "torrents_removed": ["B" * 40, "all", "not-a-hash"],
    }
    snapshot = sync_payload(torrent=raw_torrent(progress=0.5))
    gateway = Mock()
    gateway.sync.return_value = (delta, snapshot)

    result = asyncio.run(enabled_service(gateway).sync(7))

    torrent = result.torrents[TORRENT_HASH.lower()]
    assert torrent.name == "Example.Show.S01E01"
    assert torrent.progress == 0.5
    assert result.full_update is False
    assert result.removed == ["b" * 40]


def test_disabled_bridge_fails_before_gateway_call() -> None:
    gateway = Mock()
    service = QbittorrentBridgeService(
        QbittorrentConfig(enabled=False),
        gateway=gateway,
    )

    with pytest.raises(QbittorrentDisabledError):
        asyncio.run(service.sync(0))

    gateway.sync.assert_not_called()


def test_mutations_delegate_exact_hash_and_delete_semantics() -> None:
    gateway = Mock()
    service = enabled_service(gateway)
    normalized_hash = TORRENT_HASH.lower()

    asyncio.run(service.pause(normalized_hash))
    asyncio.run(service.resume(normalized_hash))
    asyncio.run(service.delete(normalized_hash, delete_files=False))
    asyncio.run(service.delete(normalized_hash, delete_files=True))

    gateway.pause.assert_called_once_with(normalized_hash)
    gateway.resume.assert_called_once_with(normalized_hash)
    assert gateway.delete.call_args_list[0].kwargs == {"delete_files": False}
    assert gateway.delete.call_args_list[1].kwargs == {"delete_files": True}


def test_add_uses_secret_magnet_without_returning_it() -> None:
    gateway = Mock()
    gateway.add_magnet.return_value = "MediaManager"
    service = enabled_service(gateway)
    magnet = f"magnet:?xt=urn:btih:{TORRENT_HASH}&dn=Example"

    result = asyncio.run(
        service.add(QbAddRequest(magnet_uri=magnet, category="MediaManager"))
    )

    assert result.model_dump() == {"accepted": True, "category": "MediaManager"}
    gateway.add_magnet.assert_called_once_with(magnet, "MediaManager")


@pytest.mark.parametrize(
    "value",
    ["all", "../torrent", "abc?delete=true", "a" * 39, "z" * 40],
)
def test_hash_validation_rejects_qbittorrent_special_and_path_values(
    value: str,
) -> None:
    with pytest.raises(ValidationError):
        validate_qbittorrent_hash(value)


@pytest.mark.parametrize(
    "value",
    ["https://example.invalid/file.torrent", "magnet:?dn=missing-exact-topic", ""],
)
def test_add_rejects_non_bittorrent_magnets(value: str) -> None:
    gateway = Mock()
    with pytest.raises(QbittorrentInvalidMagnetError):
        asyncio.run(enabled_service(gateway).add(QbAddRequest(magnet_uri=value)))
    gateway.add_magnet.assert_not_called()
