# ruff: noqa: S101

import hashlib
import hmac
from uuid import uuid4

from media_manager.trakt.schemas import TraktImportItem, TraktImportRequest
from media_manager.trakt.service import TraktService


def _state_service() -> TraktService:
    service = object.__new__(TraktService)
    service._state_secret = b"trakt-state-test-secret"
    return service


def test_oauth_state_round_trip_and_tamper_rejection() -> None:
    service = _state_service()
    user_id = uuid4()

    state = service._sign_state(user_id)

    assert service._verify_state(state) == user_id
    encoded, signature = state.split(".", maxsplit=1)
    replacement = "0" if signature[-1] != "0" else "1"
    assert service._verify_state(f"{encoded}.{signature[:-1]}{replacement}") is None
    assert service._verify_state("not-a-valid-state") is None


def test_oauth_state_rejects_payload_signed_with_another_secret() -> None:
    service = _state_service()
    state = service._sign_state(uuid4())
    encoded, _signature = state.split(".", maxsplit=1)
    wrong_signature = hmac.new(
        b"another-secret",
        encoded.encode(),
        hashlib.sha256,
    ).hexdigest()

    assert service._verify_state(f"{encoded}.{wrong_signature}") is None


def test_normalize_items_deduplicates_and_preserves_real_sources() -> None:
    movie = {
        "movie": {
            "title": "Arrival",
            "year": 2016,
            "ids": {"trakt": 10, "tmdb": 329865, "imdb": "tt2543164"},
        }
    }
    duplicate_movie = {
        "movie": {
            "title": "Arrival",
            "year": 2016,
            "ids": {"trakt": 10, "tmdb": 329865},
        }
    }
    show = {
        "show": {
            "title": "Dark",
            "year": 2017,
            "ids": {"trakt": 20, "tmdb": 70523, "tvdb": 334824},
        }
    }

    items = TraktService._normalize_items(
        [
            ("watchlist", [movie, {"movie": {"title": "Missing IDs"}}]),
            ("collection", [duplicate_movie, show]),
            ("list:Favorites", [duplicate_movie, "invalid-row"]),
        ]
    )

    assert [item.key for item in items] == ["movie:329865", "show:70523"]
    assert items[0].sources == ["watchlist", "collection", "list:Favorites"]
    assert items[0].ids.imdb == "tt2543164"
    assert items[1].title == "Dark"


def test_bulk_import_schema_deduplicates_same_media_identity() -> None:
    request = TraktImportRequest(
        items=[
            TraktImportItem(media_type="movie", tmdb_id=329865, title="Arrival"),
            TraktImportItem(media_type="movie", tmdb_id=329865, title="Arrival"),
            TraktImportItem(media_type="show", tmdb_id=329865, title="Other"),
        ]
    )

    assert [(item.media_type, item.tmdb_id) for item in request.items] == [
        ("movie", 329865),
        ("show", 329865),
    ]

