# ruff: noqa: S101, S105, S106

import logging
from collections.abc import Mapping
from typing import Any

import pytest
from pydantic import ValidationError

from media_manager.downloads.exceptions import (
    QbittorrentCategoryNotFoundError,
    QbittorrentTorrentNotFoundError,
    QbittorrentUnavailableError,
)
from media_manager.downloads.qbittorrent import QbittorrentGateway
from media_manager.torrent.config import QbittorrentConfig

TORRENT_HASH = "a" * 40


class FakeClient:
    def __init__(self) -> None:
        self.logged_in = False
        self.logged_out = False
        self.exists = True
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.add_answer: object = "Ok."
        self.categories: Mapping[str, Any] = {"MediaManager": {}}

    def auth_log_in(self) -> None:
        self.logged_in = True

    def auth_log_out(self) -> None:
        self.logged_out = True

    def torrents_info(self, **kwargs: object) -> list[dict[str, str]]:
        self.calls.append(("info", kwargs))
        return [{"hash": TORRENT_HASH}] if self.exists else []

    def torrents_stop(self, **kwargs: object) -> None:
        self.calls.append(("stop", kwargs))

    def torrents_start(self, **kwargs: object) -> None:
        self.calls.append(("start", kwargs))

    def torrents_delete(self, **kwargs: object) -> None:
        self.calls.append(("delete", kwargs))

    def torrents_categories(self) -> Mapping[str, Any]:
        return self.categories

    def torrents_add(self, **kwargs: object) -> object:
        self.calls.append(("add", kwargs))
        return self.add_answer

    def sync_maindata(self, *, rid: int) -> dict[str, object]:
        self.calls.append(("sync", {"rid": rid}))
        return {"rid": rid + 1}


def gateway_with(client: FakeClient) -> QbittorrentGateway:
    def factory(**_kwargs: object) -> FakeClient:
        return client

    return QbittorrentGateway(
        QbittorrentConfig(
            enabled=True,
            host="qbittorrent",
            username="admin",
            password="super-secret-password",
            category_name="MediaManager",
        ),
        client_factory=factory,  # type: ignore[arg-type]
    )


def test_gateway_uses_v5_compatible_start_stop_and_exact_delete_flag() -> None:
    client = FakeClient()
    gateway = gateway_with(client)

    gateway.pause(TORRENT_HASH)
    gateway.resume(TORRENT_HASH)
    gateway.delete(TORRENT_HASH, delete_files=False)
    gateway.delete(TORRENT_HASH, delete_files=True)

    assert ("stop", {"torrent_hashes": TORRENT_HASH}) in client.calls
    assert ("start", {"torrent_hashes": TORRENT_HASH}) in client.calls
    assert (
        "delete",
        {"torrent_hashes": TORRENT_HASH, "delete_files": False},
    ) in client.calls
    assert (
        "delete",
        {"torrent_hashes": TORRENT_HASH, "delete_files": True},
    ) in client.calls
    assert client.logged_out is True


def test_gateway_refuses_special_all_hash_before_login() -> None:
    client = FakeClient()

    with pytest.raises(ValidationError):
        gateway_with(client).delete("all", delete_files=True)

    assert client.logged_in is False
    assert client.calls == []


def test_gateway_checks_existence_before_mutation() -> None:
    client = FakeClient()
    client.exists = False

    with pytest.raises(QbittorrentTorrentNotFoundError):
        gateway_with(client).pause(TORRENT_HASH)

    assert not any(name == "stop" for name, _arguments in client.calls)
    assert client.logged_out is True


def test_add_defaults_to_configured_existing_category() -> None:
    client = FakeClient()
    magnet = f"magnet:?xt=urn:btih:{TORRENT_HASH}"

    category = gateway_with(client).add_magnet(magnet, None)

    assert category == "MediaManager"
    add_call = next(arguments for name, arguments in client.calls if name == "add")
    assert add_call == {"urls": magnet, "category": "MediaManager"}


def test_add_rejects_unknown_category_without_submitting_magnet() -> None:
    client = FakeClient()

    with pytest.raises(QbittorrentCategoryNotFoundError):
        gateway_with(client).add_magnet(
            f"magnet:?xt=urn:btih:{TORRENT_HASH}",
            "unknown",
        )

    assert not any(name == "add" for name, _arguments in client.calls)


def test_gateway_failure_logs_only_exception_type(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "super-secret-password"

    def failing_factory(**_kwargs: object) -> FakeClient:
        error_message = f"connection failed with {secret}"
        raise RuntimeError(error_message)

    gateway = QbittorrentGateway(
        QbittorrentConfig(enabled=True, password=secret),
        client_factory=failing_factory,  # type: ignore[arg-type]
    )
    caplog.set_level(logging.WARNING)

    with pytest.raises(QbittorrentUnavailableError):
        gateway.sync(0)

    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text
