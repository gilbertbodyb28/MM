import logging
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any, cast

import qbittorrentapi

from media_manager.downloads.exceptions import (
    QbittorrentBridgeError,
    QbittorrentCategoryNotFoundError,
    QbittorrentTorrentNotFoundError,
    QbittorrentUnavailableError,
)
from media_manager.downloads.schemas import validate_qbittorrent_hash
from media_manager.torrent.config import QbittorrentConfig

log = logging.getLogger(__name__)

ClientFactory = Callable[..., qbittorrentapi.Client]


class QbittorrentGateway:
    """Small qBittorrent boundary that never exposes credentials or raw payloads."""

    def __init__(
        self,
        config: QbittorrentConfig,
        client_factory: ClientFactory = qbittorrentapi.Client,
    ) -> None:
        self.config = config
        self.client_factory = client_factory

    @contextmanager
    def _session(self) -> Iterator[qbittorrentapi.Client]:
        client: qbittorrentapi.Client | None = None
        try:
            client = self.client_factory(
                host=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
                REQUESTS_ARGS={"timeout": 15},
            )
            client.auth_log_in()
            yield client
        except QbittorrentBridgeError:
            raise
        except Exception as error:
            log.warning(
                "qBittorrent bridge request failed (%s)",
                type(error).__name__,
            )
            raise QbittorrentUnavailableError from error
        finally:
            if client is not None:
                try:
                    client.auth_log_out()
                except Exception as error:
                    log.debug(
                        "qBittorrent bridge logout failed (%s)",
                        type(error).__name__,
                    )

    def sync(self, rid: int) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return the requested delta plus a current full snapshot for hydration."""
        with self._session() as client:
            delta = cast(dict[str, Any], client.sync_maindata(rid=rid))
            if rid == 0:
                return delta, delta
            snapshot = cast(dict[str, Any], client.sync_maindata(rid=0))
            return delta, snapshot

    @staticmethod
    def _require_torrent(client: qbittorrentapi.Client, torrent_hash: str) -> None:
        if not client.torrents_info(torrent_hashes=torrent_hash):
            raise QbittorrentTorrentNotFoundError

    def pause(self, torrent_hash: str) -> None:
        torrent_hash = validate_qbittorrent_hash(torrent_hash)
        with self._session() as client:
            self._require_torrent(client, torrent_hash)
            # qbittorrent-api maps this to pause before qB v5 and stop on qB v5+.
            client.torrents_stop(torrent_hashes=torrent_hash)

    def resume(self, torrent_hash: str) -> None:
        torrent_hash = validate_qbittorrent_hash(torrent_hash)
        with self._session() as client:
            self._require_torrent(client, torrent_hash)
            # qbittorrent-api maps this to resume before qB v5 and start on qB v5+.
            client.torrents_start(torrent_hashes=torrent_hash)

    def delete(self, torrent_hash: str, *, delete_files: bool) -> None:
        torrent_hash = validate_qbittorrent_hash(torrent_hash)
        with self._session() as client:
            self._require_torrent(client, torrent_hash)
            client.torrents_delete(
                torrent_hashes=torrent_hash,
                delete_files=delete_files,
            )

    def add_magnet(self, magnet_uri: str, category: str | None) -> str:
        with self._session() as client:
            target_category = category or self.config.category_name
            categories = cast(Mapping[str, Any], client.torrents_categories())
            if target_category not in categories:
                raise QbittorrentCategoryNotFoundError
            answer = client.torrents_add(
                urls=magnet_uri,
                category=target_category,
            )
            success_count = getattr(answer, "success_count", 0)
            pending_count = getattr(answer, "pending_count", 0)
            accepted = (
                answer == "Ok."
                or (isinstance(success_count, int) and success_count > 0)
                or (isinstance(pending_count, int) and pending_count > 0)
            )
            if not accepted:
                raise QbittorrentUnavailableError
            return target_category
