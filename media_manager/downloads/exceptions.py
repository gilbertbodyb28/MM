class QbittorrentBridgeError(Exception):
    """Base error for sanitized qBittorrent bridge failures."""


class QbittorrentDisabledError(QbittorrentBridgeError):
    """Raised when qBittorrent is disabled in MediaManager settings."""


class QbittorrentUnavailableError(QbittorrentBridgeError):
    """Raised when qBittorrent cannot be contacted or rejects a command."""


class QbittorrentTorrentNotFoundError(QbittorrentBridgeError):
    """Raised when an exact torrent hash is not present in qBittorrent."""


class QbittorrentCategoryNotFoundError(QbittorrentBridgeError):
    """Raised when a requested qBittorrent category does not exist."""


class QbittorrentInvalidMagnetError(QbittorrentBridgeError):
    """Raised when a submitted magnet is not a bounded BitTorrent magnet."""
