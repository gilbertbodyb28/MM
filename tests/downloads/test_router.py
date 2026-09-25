# ruff: noqa: S101, S105

from unittest.mock import AsyncMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from media_manager.auth.users import current_superuser
from media_manager.downloads.dependencies import get_qbittorrent_bridge_service
from media_manager.downloads.exceptions import QbittorrentInvalidMagnetError
from media_manager.downloads.router import router
from media_manager.downloads.schemas import QbAddResponse

TORRENT_HASH = "a" * 40


def client_with(service: AsyncMock, *, authorized: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/downloads/qbittorrent")
    app.dependency_overrides[get_qbittorrent_bridge_service] = lambda: service
    if authorized:
        app.dependency_overrides[current_superuser] = lambda: object()
    else:

        def deny() -> None:
            raise HTTPException(status_code=403, detail="Forbidden")

        app.dependency_overrides[current_superuser] = deny
    return TestClient(app)


def test_every_route_requires_superuser() -> None:
    service = AsyncMock()
    client = client_with(service, authorized=False)

    response = client.get("/api/v1/downloads/qbittorrent/sync")

    assert response.status_code == 403
    service.sync.assert_not_awaited()


def test_path_rejects_special_all_before_service_call() -> None:
    service = AsyncMock()
    client = client_with(service)

    response = client.post("/api/v1/downloads/qbittorrent/all/pause")

    assert response.status_code == 422
    service.pause.assert_not_awaited()


def test_pause_and_resume_return_explicit_actions() -> None:
    service = AsyncMock()
    client = client_with(service)

    paused = client.post(f"/api/v1/downloads/qbittorrent/{TORRENT_HASH}/pause")
    resumed = client.post(f"/api/v1/downloads/qbittorrent/{TORRENT_HASH}/resume")

    assert paused.status_code == 202
    assert paused.json() == {
        "hash": TORRENT_HASH,
        "action": "pause",
        "accepted": True,
    }
    assert resumed.status_code == 202
    assert resumed.json()["action"] == "resume"


def test_delete_requires_explicit_file_semantics() -> None:
    service = AsyncMock()
    client = client_with(service)
    path = f"/api/v1/downloads/qbittorrent/{TORRENT_HASH}"

    missing = client.delete(path)
    keep_files = client.delete(path, params={"delete_files": "false"})
    delete_files = client.delete(path, params={"delete_files": "true"})

    assert missing.status_code == 422
    assert keep_files.json() == {"hash": TORRENT_HASH, "files_deleted": False}
    assert delete_files.json() == {"hash": TORRENT_HASH, "files_deleted": True}
    assert service.delete.await_args_list[0].kwargs == {"delete_files": False}
    assert service.delete.await_args_list[1].kwargs == {"delete_files": True}


def test_add_accepts_magnet_without_echoing_it() -> None:
    service = AsyncMock()
    service.add.return_value = QbAddResponse(category="MediaManager")
    client = client_with(service)
    magnet = f"magnet:?xt=urn:btih:{TORRENT_HASH}&dn=private-name"

    response = client.post(
        "/api/v1/downloads/qbittorrent/add",
        json={"magnet_uri": magnet, "category": "MediaManager"},
    )

    assert response.status_code == 202
    assert response.json() == {"accepted": True, "category": "MediaManager"}
    assert magnet not in response.text


def test_invalid_magnet_is_not_reflected_in_validation_response() -> None:
    service = AsyncMock()
    service.add.side_effect = QbittorrentInvalidMagnetError
    client = client_with(service)
    secret = "VERY-PRIVATE-PASSKEY"

    response = client.post(
        "/api/v1/downloads/qbittorrent/add",
        json={"magnet_uri": f"https://invalid.example/file?passkey={secret}"},
    )

    assert response.status_code == 422
    assert secret not in response.text
