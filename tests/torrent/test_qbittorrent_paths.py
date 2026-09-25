# ruff: noqa: S101

from media_manager.torrent.download_clients.qbittorrent import (
    _download_directory_name,
    _download_path,
)


def test_download_directory_name_blocks_path_traversal() -> None:
    directory_name = _download_directory_name("../../unsafe/title", "abc123")

    assert "/" not in directory_name
    assert "\\" not in directory_name
    assert directory_name not in {"", ".", ".."}


def test_download_directory_name_falls_back_to_hash() -> None:
    assert _download_directory_name("..", "abc123") == "abc123"


def test_download_path_uses_configured_posix_root() -> None:
    assert _download_path("/data/torrents", "Release.Name") == (
        "/data/torrents/Release.Name"
    )


def test_download_path_supports_windows_qbittorrent_hosts() -> None:
    assert _download_path(r"D:\Media\Torrents", "Release.Name") == (
        r"D:\Media\Torrents\Release.Name"
    )
