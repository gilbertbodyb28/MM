# ruff: noqa: S101

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from media_manager.recommendations.clients import (
    OllamaClient,
    PlexClient,
    TautulliClient,
)
from media_manager.recommendations.config import (
    OllamaRecommendationConfig,
    PlexRecommendationConfig,
    TautulliRecommendationConfig,
)
from media_manager.recommendations.exceptions import OllamaResponseError
from media_manager.recommendations.schemas import (
    HistoryEventType,
    TasteHistoryEntry,
    TasteProfile,
)


def test_tautulli_history_and_statistics_are_normalized() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        command = request.url.params["cmd"]
        if command == "get_history":
            data: object = {
                "data": [
                    {
                        "row_id": 42,
                        "user_id": 7,
                        "rating_key": "123",
                        "media_type": "episode",
                        "title": "The One With Tests",
                        "grandparent_title": "Example Show",
                        "year": 2024,
                        "date": 1_700_000_000,
                        "duration": 1_800,
                        "play_duration": 900,
                        "genres": ["Comedy", "Comedy"],
                        "user_rating": 8,
                    }
                ]
            }
        else:
            data = [
                {
                    "stat_id": "top_tv",
                    "rows": [
                        {
                            "title": "Example Show",
                            "media_type": "show",
                            "total_plays": 5,
                            "total_duration": 9_000,
                        }
                    ],
                }
            ]
        return httpx.Response(
            200,
            json={"response": {"result": "success", "data": data}},
        )

    async def exercise() -> tuple[object, object]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = TautulliClient(
                TautulliRecommendationConfig(
                    enabled=True,
                    api_key=SecretStr("tautulli-secret"),
                ),
                client=http_client,
            )
            return (
                await client.get_history("7"),
                await client.get_statistics("7"),
            )

    history, statistics = asyncio.run(exercise())
    item = history[0]
    assert item.source_event_id == "42"
    assert item.series_title == "Example Show"
    assert item.genres == ["Comedy"]
    assert item.watch_duration_seconds == 900
    assert statistics[0].play_count == 5
    assert all(
        request.url.params["apikey"] == "tautulli-secret" for request in requests
    )
    history_request = next(
        request for request in requests if request.url.params["cmd"] == "get_history"
    )
    assert history_request.url.params["grouping"] == "0"


def test_plex_history_and_webhook_are_idempotently_normalized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Plex-Token"] == "plex-secret"
        assert request.url.params["accountID"] == "9"
        return httpx.Response(
            200,
            json={
                "MediaContainer": {
                    "Metadata": [
                        {
                            "ratingKey": "88",
                            "type": "movie",
                            "title": "Example Movie",
                            "year": 2023,
                            "viewedAt": 1_700_000_000,
                            "duration": 7_200_000,
                            "viewOffset": 7_000_000,
                        }
                    ]
                }
            },
        )

    async def exercise() -> object:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = PlexClient(
                PlexRecommendationConfig(
                    enabled=True,
                    token=SecretStr("plex-secret"),
                ),
                client=http_client,
            )
            return await client.get_history("9")

    history = asyncio.run(exercise())
    assert history[0].completion_percent == pytest.approx(97.22, rel=0.01)

    payload = {
        "event": "media.rate",
        "Account": {"id": 9, "title": "Viewer"},
        "Server": {"uuid": "server-id"},
        "Metadata": {
            "ratingKey": "88",
            "type": "movie",
            "title": "Example Movie",
            "year": 2023,
            "updatedAt": 1_700_000_000,
            "userRating": 9,
        },
    }
    first = PlexClient.parse_webhook(payload)
    second = PlexClient.parse_webhook(payload)
    assert first is not None
    assert second is not None
    assert first.history_item.event_type == HistoryEventType.RATING
    assert first.server_id == "server-id"
    assert first.history_item.source_event_id == second.history_item.source_event_id
    assert first.history_item.rating == 9


def test_plex_watched_library_collapses_episodes_to_parent_series() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Plex-Token"] == "plex-secret"
        if request.url.path == "/library/sections":
            return httpx.Response(
                200,
                json={
                    "MediaContainer": {
                        "Directory": [
                            {"key": "1", "type": "show", "title": "TV"},
                            {"key": "2", "type": "movie", "title": "Movies"},
                        ]
                    }
                },
            )

        assert request.url.params["accountID"] == "9"
        if (
            request.url.path == "/library/sections/1/all"
            and request.url.params.get("type") == "4"
        ):
            rows = [
                {
                    "ratingKey": "101",
                    "type": "episode",
                    "title": "Episode One",
                    "grandparentRatingKey": "10",
                    "grandparentTitle": "Example Show",
                    "viewCount": 1,
                    "viewedAt": 1_700_000_000,
                },
                {
                    "ratingKey": "102",
                    "type": "episode",
                    "title": "Episode Two",
                    "grandparentRatingKey": "10",
                    "grandparentTitle": "Example Show",
                    "viewCount": 2,
                    "lastViewedAt": 1_700_001_000,
                },
                {
                    "ratingKey": "103",
                    "type": "episode",
                    "title": "Unwatched",
                    "grandparentRatingKey": "10",
                    "grandparentTitle": "Example Show",
                },
            ]
        elif request.url.path == "/library/sections/1/all":
            rows = [
                {
                    "ratingKey": "10",
                    "type": "show",
                    "title": "Example Show",
                    "year": 2024,
                    "Guid": [
                        {"id": "tmdb://321"},
                        {"id": "tvdb://654"},
                    ],
                }
            ]
        else:
            rows = [
                {
                    "ratingKey": "20",
                    "type": "movie",
                    "title": "Example Movie",
                    "year": 2023,
                    "viewCount": 1,
                    "viewedAt": 1_699_999_000,
                    "Guid": [{"id": "imdb://tt1234567"}],
                },
                {
                    "ratingKey": "21",
                    "type": "movie",
                    "title": "Unwatched Movie",
                    "year": 2025,
                },
            ]
        return httpx.Response(200, json={"MediaContainer": {"Metadata": rows}})

    async def exercise() -> object:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = PlexClient(
                PlexRecommendationConfig(
                    enabled=True,
                    token=SecretStr("plex-secret"),
                ),
                client=http_client,
            )
            return await client.get_watched_library_history("9")

    history = asyncio.run(exercise())
    assert len(history) == 2
    show = next(item for item in history if item.media_type == "show")
    movie = next(item for item in history if item.media_type == "movie")
    assert show.title == "Example Show"
    assert show.source_media_id == "10"
    assert show.external_ids == {"tmdb": "321", "tvdb": "654", "plex": "10"}
    assert show.watched_at == datetime.fromtimestamp(1_700_001_000, tz=UTC)
    assert movie.title == "Example Movie"
    assert movie.external_ids == {"imdb": "tt1234567", "plex": "20"}


def test_ollama_uses_json_schema_and_rejects_invalid_output() -> None:
    captured_body: dict[str, object] = {}

    def valid_handler(request: httpx.Request) -> httpx.Response:
        captured_body.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "llama3.2",
                "done": True,
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "recommendations": [
                                {
                                    "title": "Arrival",
                                    "media_type": "movie",
                                    "year": 2016,
                                    "reason": "Its thoughtful science fiction fits the profile.",
                                    "genres": ["Science Fiction"],
                                    "confidence": 0.9,
                                }
                            ]
                        }
                    ),
                },
            },
        )

    profile = TasteProfile(
        watched=[
            TasteHistoryEntry(
                title="Contact",
                media_type="movie",
                year=1997,
                genres=["Science Fiction"],
            )
        ],
        top_genres=["Science Fiction"],
    )

    async def valid_request() -> object:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(valid_handler)
        ) as http_client:
            client = OllamaClient(
                OllamaRecommendationConfig(enabled=True),
                client=http_client,
            )
            return await client.generate_recommendations(profile, 1)

    batch = asyncio.run(valid_request())
    assert batch.recommendations[0].title == "Arrival"
    assert isinstance(captured_body["format"], dict)
    assert captured_body["stream"] is False
    assert captured_body["options"] == {"temperature": 0.25}

    def invalid_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "llama3.2",
                "done": True,
                "message": {
                    "role": "assistant",
                    "content": '{"recommendations":[{"title":"Unvalidated"}]}',
                },
            },
        )

    async def invalid_request() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(invalid_handler)
        ) as http_client:
            client = OllamaClient(
                OllamaRecommendationConfig(enabled=True),
                client=http_client,
            )
            await client.generate_recommendations(profile, 1)

    with pytest.raises(OllamaResponseError):
        asyncio.run(invalid_request())


def test_client_config_repr_does_not_expose_secrets() -> None:
    config = PlexRecommendationConfig(
        enabled=True,
        token=SecretStr("do-not-leak"),
        webhook_enabled=True,
        webhook_secret=SecretStr("also-private"),
    )
    assert "do-not-leak" not in repr(config)
    assert "also-private" not in repr(config)
    assert datetime.now(UTC).tzinfo is UTC


def test_plex_server_uuid_is_optional_and_normalized() -> None:
    config = PlexRecommendationConfig(server_uuid="  SERVER-ID  ")
    assert config.server_uuid == "server-id"
    assert PlexRecommendationConfig(server_uuid="  ").server_uuid is None


@pytest.mark.parametrize(
    "config_factory",
    [
        lambda: TautulliRecommendationConfig(
            enabled=True,
            api_key=SecretStr(""),
        ),
        lambda: PlexRecommendationConfig(
            enabled=True,
            token=SecretStr("   "),
        ),
        lambda: PlexRecommendationConfig(
            webhook_enabled=True,
            webhook_secret=SecretStr(""),
        ),
    ],
)
def test_enabled_integrations_reject_blank_secrets(
    config_factory: Callable[[], object],
) -> None:
    with pytest.raises(ValidationError):
        config_factory()
