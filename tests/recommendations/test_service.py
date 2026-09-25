# ruff: noqa: S101

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from media_manager.recommendations.config import (
    OllamaRecommendationConfig,
    PlexRecommendationConfig,
    RecommendationConfig,
    RecommendationUserMapping,
    TautulliRecommendationConfig,
)
from media_manager.recommendations.exceptions import (
    RecommendationConfigurationError,
    RecommendationRefreshInProgressError,
)
from media_manager.recommendations.router import refresh_recommendations
from media_manager.recommendations.schemas import (
    GeneratedRecommendation,
    GeneratedRecommendationBatch,
    HistorySource,
    RecommendationSchema,
    RecommendationUserMappingSchema,
    SourceHistoryItem,
    SourceMetadata,
    SyncStateSchema,
    WatchHistoryItemSchema,
)
from media_manager.recommendations.service import RecommendationService


class FakeRepository:
    def __init__(self) -> None:
        self.mapping: RecommendationUserMappingSchema | None = None
        self.history: dict[tuple[UUID, str, str], WatchHistoryItemSchema] = {}
        self.recommendations: list[RecommendationSchema] = []
        self.states: list[SyncStateSchema] = []
        self.active_lease_id: UUID | None = None
        self.force_lease_occupied = False

    async def upsert_mapping(
        self,
        mapping: RecommendationUserMappingSchema,
    ) -> RecommendationUserMappingSchema:
        self.mapping = mapping
        return mapping

    async def get_mapping(
        self,
        _user_id: UUID,
    ) -> RecommendationUserMappingSchema | None:
        return self.mapping

    async def list_enabled_mappings(self) -> list[RecommendationUserMappingSchema]:
        if self.mapping is None or not self.mapping.enabled:
            return []
        return [self.mapping]

    async def get_mapping_by_plex_identity(
        self,
        _account_id: str | None,
        _username: str | None,
    ) -> RecommendationUserMappingSchema | None:
        return self.mapping

    async def insert_history(self, items: list[WatchHistoryItemSchema]) -> int:
        inserted = 0
        for item in items:
            key = (item.user_id, item.source.value, item.source_event_id)
            if key not in self.history:
                self.history[key] = item
                inserted += 1
        return inserted

    async def get_recent_history(
        self,
        user_id: UUID,
        *,
        limit: int,
    ) -> list[WatchHistoryItemSchema]:
        matching = [item for item in self.history.values() if item.user_id == user_id]
        return sorted(matching, key=lambda item: item.watched_at, reverse=True)[:limit]

    async def history_count(self, user_id: UUID) -> int:
        return sum(item.user_id == user_id for item in self.history.values())

    async def replace_recommendations(
        self,
        _user_id: UUID,
        recommendations: list[RecommendationSchema],
    ) -> None:
        self.recommendations = recommendations

    async def list_recommendations(
        self,
        _user_id: UUID,
        *,
        limit: int,
        include_expired: bool = False,
    ) -> list[RecommendationSchema]:
        del include_expired
        return self.recommendations[:limit]

    async def recommendation_count(self, _user_id: UUID) -> int:
        return len(self.recommendations)

    async def get_sync_states(self, _user_id: UUID) -> list[SyncStateSchema]:
        return self.states

    async def try_acquire_refresh_lease(
        self,
        user_id: UUID,
        source: HistorySource,
        *,
        lease_id: UUID,
        started_at: datetime,
        expires_at: datetime,
    ) -> bool:
        if self.force_lease_occupied or self.active_lease_id is not None:
            return False
        self.active_lease_id = lease_id
        self.states = [
            SyncStateSchema(
                user_id=user_id,
                source=source,
                last_sync_started_at=started_at,
                refresh_lease_id=lease_id,
                refresh_lease_expires_at=expires_at,
            )
        ]
        return True

    async def release_refresh_lease(
        self,
        _user_id: UUID,
        _source: HistorySource,
        lease_id: UUID,
    ) -> None:
        if self.active_lease_id == lease_id:
            self.active_lease_id = None

    async def mark_sync_started(
        self,
        user_id: UUID,
        source: HistorySource,
        started_at: datetime,
    ) -> None:
        self.states = [
            SyncStateSchema(
                user_id=user_id,
                source=source,
                last_sync_started_at=started_at,
            )
        ]

    async def mark_sync_success(
        self,
        user_id: UUID,
        source: HistorySource,
        *,
        cursor: str | None,
        completed_at: datetime,
        generated_at: datetime | None,
    ) -> None:
        self.states = [
            SyncStateSchema(
                user_id=user_id,
                source=source,
                last_cursor=cursor,
                last_sync_completed_at=completed_at,
                last_generated_at=generated_at,
            )
        ]

    async def mark_sync_failure(
        self,
        _user_id: UUID,
        _source: HistorySource,
        _error_message: str,
    ) -> None:
        return


class FakeTautulliClient:
    def __init__(self) -> None:
        self.history_calls = 0

    async def get_history(
        self,
        _user_id: str,
        *,
        start: int = 0,
        length: int = 100,
    ) -> list[SourceHistoryItem]:
        del length
        self.history_calls += 1
        if start > 0:
            return []
        watched_at = datetime(2025, 1, 1, tzinfo=UTC)
        return [
            SourceHistoryItem(
                source=HistorySource.TAUTULLI,
                source_event_id=f"event-{index}",
                media_type="movie",
                title=title,
                year=year,
                genres=["Science Fiction"],
                watched_at=watched_at,
            )
            for index, (title, year) in enumerate(
                [("Contact", 1997), ("Moon", 2009), ("Arrival", 2016)]
            )
        ]

    async def get_statistics(self, _user_id: str) -> list[object]:
        return []

    async def get_metadata(self, _rating_key: str) -> SourceMetadata:
        return SourceMetadata()


class FakePlexClient:
    def __init__(self) -> None:
        self.playback_calls = 0
        self.watched_library_calls = 0

    async def get_history(
        self,
        _account_id: str,
        *,
        start: int = 0,
        size: int = 100,
    ) -> list[SourceHistoryItem]:
        del size
        self.playback_calls += 1
        if start > 0:
            return []
        return [
            SourceHistoryItem(
                source=HistorySource.PLEX,
                source_event_id="playback-movie",
                source_media_id="20",
                media_type="movie",
                title="Example Movie",
                watched_at=datetime(2025, 1, 1, tzinfo=UTC),
            )
        ]

    async def get_watched_library_history(
        self,
        _account_id: str,
        *,
        maximum: int = 25_000,
    ) -> list[SourceHistoryItem]:
        del maximum
        self.watched_library_calls += 1
        return [
            SourceHistoryItem(
                source=HistorySource.PLEX,
                source_event_id="watched-show",
                source_media_id="10",
                media_type="show",
                title="Example Show",
                watched_at=datetime(2025, 1, 2, tzinfo=UTC),
                external_ids={"tmdb": "321", "plex": "10"},
            )
        ]


class FakeOllamaClient:
    async def generate_recommendations(
        self,
        _profile: object,
        _count: int,
        *,
        excluded_titles: list[tuple[str, str]] | None = None,
    ) -> GeneratedRecommendationBatch:
        excluded = set(excluded_titles or [])
        fresh_title = "Solaris" if ("movie", "gattaca") in excluded else "Gattaca"
        return GeneratedRecommendationBatch(
            recommendations=[
                GeneratedRecommendation(
                    title="Arrival",
                    media_type="movie",
                    year=2016,
                    reason="This duplicate should be filtered from the final result.",
                    genres=["Science Fiction"],
                    confidence=0.9,
                ),
                GeneratedRecommendation(
                    title=fresh_title,
                    media_type="movie",
                    year=1972 if fresh_title == "Solaris" else 1997,
                    reason="Thoughtful science fiction matches the established taste.",
                    genres=["Science Fiction"],
                    confidence=0.85,
                ),
            ]
        )


class BlockingTautulliClient(FakeTautulliClient):
    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def get_history(
        self,
        user_id: str,
        *,
        start: int = 0,
        length: int = 100,
    ) -> list[SourceHistoryItem]:
        if start == 0:
            self.entered.set()
            await self.release.wait()
        return await super().get_history(
            user_id,
            start=start,
            length=length,
        )


def build_service() -> tuple[
    RecommendationService,
    FakeRepository,
    FakeTautulliClient,
    UUID,
]:
    user_id = uuid4()
    repository = FakeRepository()
    tautulli = FakeTautulliClient()
    config = RecommendationConfig(
        enabled=True,
        history_provider="tautulli",
        history_page_size=100,
        minimum_history_items=3,
        metadata_enrichment_limit=0,
        tautulli=TautulliRecommendationConfig(
            enabled=True,
            api_key=SecretStr("secret"),
        ),
        ollama=OllamaRecommendationConfig(enabled=True),
        users=[
            RecommendationUserMapping(
                user_id=user_id,
                tautulli_user_id="7",
            )
        ],
    )
    service = RecommendationService(
        repository=repository,  # type: ignore[arg-type]
        config=config,
        tautulli_client=tautulli,  # type: ignore[arg-type]
        ollama_client=FakeOllamaClient(),  # type: ignore[arg-type]
    )
    return service, repository, tautulli, user_id


def test_refresh_filters_watched_titles_and_generates_a_fresh_set() -> None:
    service, repository, _tautulli, user_id = build_service()

    async def exercise() -> tuple[object, object]:
        return await service.refresh_user(user_id), await service.refresh_user(user_id)

    first, second = asyncio.run(exercise())
    assert first.history_items_inserted == 3
    assert second.history_items_inserted == 0
    assert first.recommendations_generated == 1
    assert second.recommendations_generated == 1
    assert [item.name for item in repository.recommendations] == ["Solaris"]
    assert repository.recommendations[0].rank == 1
    assert repository.recommendations[0].reason.startswith(
        "Because you watched Contact"
    )
    assert "duplicate should" not in repository.recommendations[0].reason
    assert "user_id" not in repository.recommendations[0].model_dump(by_alias=True)


def test_plex_fetch_combines_playback_history_with_watched_library_state() -> None:
    repository = FakeRepository()
    plex = FakePlexClient()
    config = RecommendationConfig(
        enabled=True,
        history_provider="plex",
        history_page_size=100,
        max_history_items_per_sync=500,
        plex=PlexRecommendationConfig(
            enabled=True,
            token=SecretStr("secret"),
        ),
        ollama=OllamaRecommendationConfig(enabled=True),
    )
    service = RecommendationService(
        repository=repository,  # type: ignore[arg-type]
        config=config,
        plex_client=plex,  # type: ignore[arg-type]
    )
    mapping = RecommendationUserMappingSchema(
        user_id=uuid4(),
        plex_account_id="9",
    )

    history = asyncio.run(service._fetch_history(mapping, HistorySource.PLEX))

    assert [item.title for item in history] == ["Example Show", "Example Movie"]
    assert plex.playback_calls == 1
    assert plex.watched_library_calls == 1


def test_refresh_due_users_skips_recent_sync() -> None:
    service, repository, tautulli, user_id = build_service()
    repository.states = [
        SyncStateSchema(
            user_id=user_id,
            source=HistorySource.TAUTULLI,
            last_sync_completed_at=datetime.now(UTC),
        )
    ]
    results = asyncio.run(service.refresh_due_users())
    assert results == []
    assert tautulli.history_calls == 0


def test_disabled_config_mapping_overwrites_stale_enabled_mapping() -> None:
    _service, repository, tautulli, user_id = build_service()
    repository.mapping = RecommendationUserMappingSchema(
        user_id=user_id,
        tautulli_user_id="7",
        enabled=True,
    )
    disabled_config = RecommendationConfig(
        enabled=True,
        history_provider="tautulli",
        tautulli=TautulliRecommendationConfig(
            enabled=True,
            api_key=SecretStr("secret"),
        ),
        ollama=OllamaRecommendationConfig(enabled=True),
        users=[
            RecommendationUserMapping(
                user_id=user_id,
                tautulli_user_id="7",
                enabled=False,
            )
        ],
    )
    disabled_service = RecommendationService(
        repository=repository,  # type: ignore[arg-type]
        config=disabled_config,
        tautulli_client=tautulli,  # type: ignore[arg-type]
        ollama_client=FakeOllamaClient(),  # type: ignore[arg-type]
    )

    async def exercise() -> None:
        results = await disabled_service.refresh_due_users()
        assert results == []
        status = await disabled_service.get_status(user_id)
        assert status.mapped is False
        assert repository.mapping is not None
        assert repository.mapping.enabled is False
        with pytest.raises(RecommendationConfigurationError):
            await disabled_service.refresh_user(user_id)

    asyncio.run(exercise())


def test_concurrent_refresh_returns_409_and_scheduler_skips() -> None:
    service, repository, _tautulli, user_id = build_service()

    async def exercise() -> None:
        blocking_client = BlockingTautulliClient()
        first_service = RecommendationService(
            repository=repository,  # type: ignore[arg-type]
            config=service.config,
            tautulli_client=blocking_client,  # type: ignore[arg-type]
            ollama_client=FakeOllamaClient(),  # type: ignore[arg-type]
        )
        second_service = RecommendationService(
            repository=repository,  # type: ignore[arg-type]
            config=service.config,
            tautulli_client=blocking_client,  # type: ignore[arg-type]
            ollama_client=FakeOllamaClient(),  # type: ignore[arg-type]
        )
        active_refresh = asyncio.create_task(first_service.refresh_user(user_id))
        await blocking_client.entered.wait()
        try:
            with pytest.raises(HTTPException) as error:
                await refresh_recommendations(
                    second_service,  # type: ignore[arg-type]
                    SimpleNamespace(id=user_id),  # type: ignore[arg-type]
                )
            assert error.value.status_code == 409
            assert await second_service.refresh_due_users() == []
        finally:
            blocking_client.release.set()
        await active_refresh

    asyncio.run(exercise())


def test_database_lease_occupied_path_is_single_flight() -> None:
    service, repository, tautulli, user_id = build_service()
    repository.force_lease_occupied = True
    with pytest.raises(RecommendationRefreshInProgressError):
        asyncio.run(service.refresh_user(user_id))
    assert tautulli.history_calls == 0
    assert repository.active_lease_id is None


def test_webhook_rejects_unexpected_plex_server_before_ingest() -> None:
    repository = FakeRepository()
    config = RecommendationConfig(
        plex=PlexRecommendationConfig(
            webhook_enabled=True,
            webhook_secret=SecretStr("webhook-secret"),
            server_uuid="expected-server",
        )
    )
    service = RecommendationService(
        repository=repository,  # type: ignore[arg-type]
        config=config,
    )
    payload: dict[str, object] = {
        "event": "media.scrobble",
        "Account": {"id": "7", "title": "Viewer"},
        "Server": {"uuid": "different-server"},
        "Metadata": {
            "ratingKey": "88",
            "type": "movie",
            "title": "Example Movie",
            "viewedAt": 1_700_000_000,
        },
    }
    result = asyncio.run(service.ingest_plex_webhook(payload, "webhook-secret"))
    assert result.accepted is False
    assert result.reason == "The Plex webhook originated from an unexpected server"
    assert repository.history == {}
