# ruff: noqa: S101

import asyncio

import pytest

from media_manager.seerr.schemas import SeerrRequestCreate
from media_manager.seerr.service import SeerrService


@pytest.mark.parametrize(
    ("media_status", "request_status", "request_id", "expected"),
    [
        (5, None, None, "available"),
        (4, None, None, "partially_available"),
        (3, None, None, "processing"),
        (2, None, None, "pending"),
        (None, 2, 41, "approved"),
        (None, 3, 42, "declined"),
        (None, None, 43, "requested"),
        (None, None, None, "not_requested"),
    ],
)
def test_state_maps_seerr_media_and_request_statuses(
    media_status: int | None,
    request_status: int | None,
    request_id: int | None,
    expected: str,
) -> None:
    assert SeerrService._state(media_status, request_status, request_id) == expected


def test_normalize_status_uses_latest_request_metadata() -> None:
    status = SeerrService._normalize_status(
        "tv",
        70523,
        {
            "mediaInfo": {"status": 4},
            "requests": [{"id": 97, "status": 2}],
        },
    )

    assert status.media_type == "tv"
    assert status.tmdb_id == 70523
    assert status.status == "partially_available"
    assert status.request_id == 97
    assert status.request_status == 2


class RecordingSeerrService(SeerrService):
    def __init__(self, *, exists_in_plex: bool = False) -> None:
        self.exists_in_plex = exists_in_plex
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []

    async def _exists_in_plex(self, media_type: str, tmdb_id: int) -> bool:
        del media_type, tmdb_id
        return self.exists_in_plex

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.calls.append((method, path, json_body))
        return {"id": 51, "status": 2}


def test_tv_request_sends_selected_seasons_to_backend_only_proxy() -> None:
    service = RecordingSeerrService()

    result = asyncio.run(
        service.create_request(
            SeerrRequestCreate(media_type="tv", tmdb_id=70523, seasons=[1, 3])
        )
    )

    assert service.calls == [
        (
            "POST",
            "/request",
            {"mediaType": "tv", "mediaId": 70523, "seasons": [1, 3]},
        )
    ]
    assert result.status == "approved"
    assert result.message == "Request sent to Seerr."


def test_existing_plex_item_skips_seerr_request() -> None:
    service = RecordingSeerrService(exists_in_plex=True)

    result = asyncio.run(
        service.create_request(
            SeerrRequestCreate(media_type="movie", tmdb_id=329865)
        )
    )

    assert service.calls == []
    assert result.status == "available"
    assert "already exists in Plex" in result.message

