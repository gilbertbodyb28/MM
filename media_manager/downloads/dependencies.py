from typing import Annotated

from fastapi import Depends

from media_manager.config import MediaManagerConfig
from media_manager.downloads.service import QbittorrentBridgeService


def get_qbittorrent_bridge_service() -> QbittorrentBridgeService:
    return QbittorrentBridgeService(MediaManagerConfig().torrents.qbittorrent)


qbittorrent_bridge_service_dep = Annotated[
    QbittorrentBridgeService,
    Depends(get_qbittorrent_bridge_service),
]
