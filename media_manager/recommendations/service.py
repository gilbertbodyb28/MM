import asyncio
import logging
import threading
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import timedelta
from hmac import compare_digest
from typing import ClassVar
from uuid import UUID, uuid4

from media_manager.recommendations.catalog import TmdbRecommendationCatalog
from media_manager.recommendations.clients import (
    OllamaClient,
    PlexClient,
    TautulliClient,
)
from media_manager.recommendations.config import (
    RecommendationConfig,
    RecommendationUserMapping,
)
from media_manager.recommendations.exceptions import (
    RecommendationConfigurationError,
    RecommendationProviderError,
    RecommendationRefreshInProgressError,
    WebhookAuthenticationError,
)
from media_manager.recommendations.repository import RecommendationRepository
from media_manager.recommendations.schemas import (
    GeneratedRecommendation,
    HistorySource,
    LibraryMediaIdentity,
    PlexWebhookResult,
    ProviderSyncStatus,
    RecommendationCandidate,
    RecommendationMediaType,
    RecommendationRefreshResult,
    RecommendationSchema,
    RecommendationSectionCollection,
    RecommendationSectionItemSchema,
    RecommendationSectionSchema,
    RecommendationSource,
    RecommendationStatus,
    RecommendationUserMappingSchema,
    ResolvedRecommendationMetadata,
    SourceHistoryItem,
    SourceMetadata,
    SourceStatistic,
    TasteHistoryEntry,
    TasteProfile,
    WatchHistoryItemSchema,
    normalized_title,
    utc_now,
)

log = logging.getLogger(__name__)


MetadataResolver = Callable[
    [GeneratedRecommendation],
    Awaitable[ResolvedRecommendationMetadata | None],
]


class RecommendationService:
    _refresh_locks: ClassVar[dict[UUID, asyncio.Lock]] = {}
    _refresh_locks_guard: ClassVar[threading.Lock] = threading.Lock()

    def __init__(
        self,
        repository: RecommendationRepository,
        config: RecommendationConfig,
        *,
        tautulli_client: TautulliClient | None = None,
        plex_client: PlexClient | None = None,
        ollama_client: OllamaClient | None = None,
        recommendation_catalog: TmdbRecommendationCatalog | None = None,
        metadata_resolver: MetadataResolver | None = None,
    ) -> None:
        self.repository = repository
        self.config = config
        self.tautulli_client = tautulli_client or TautulliClient(config.tautulli)
        self.plex_client = plex_client or PlexClient(config.plex)
        self.ollama_client = ollama_client or OllamaClient(config.ollama)
        self.recommendation_catalog = (
            recommendation_catalog or TmdbRecommendationCatalog()
        )
        self.metadata_resolver = metadata_resolver

    async def list_recommendations(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
    ) -> list[RecommendationSchema]:
        return await self.repository.list_recommendations(
            user_id,
            limit=min(limit, 50),
        )

    async def get_status(self, user_id: UUID) -> RecommendationStatus:
        mapping = await self._mapping_for_user(user_id, required=False)
        states = await self.repository.get_sync_states(user_id)
        return RecommendationStatus(
            enabled=self.config.enabled,
            mapped=mapping is not None and mapping.enabled,
            selected_history_provider=self.config.history_provider,
            tautulli_configured=(
                self.config.tautulli.enabled
                and self.config.tautulli.api_key is not None
            ),
            plex_configured=(
                self.config.plex.enabled and self.config.plex.token is not None
            ),
            plex_webhook_configured=(
                self.config.plex.webhook_enabled
                and self.config.plex.webhook_secret is not None
            ),
            ollama_configured=self.config.ollama.enabled,
            history_item_count=await self.repository.history_count(user_id),
            recommendation_count=await self.repository.recommendation_count(user_id),
            sync=[
                ProviderSyncStatus(
                    source=state.source,
                    last_cursor=state.last_cursor,
                    last_sync_started_at=state.last_sync_started_at,
                    last_sync_completed_at=state.last_sync_completed_at,
                    last_generated_at=state.last_generated_at,
                    last_error=state.last_error,
                )
                for state in states
            ],
        )

    async def list_sections(
        self,
        user_id: UUID,
        *,
        limit: int | None = None,
    ) -> RecommendationSectionCollection:
        sections = await self.repository.list_sections(
            user_id,
            limit=min(limit or self.config.section_count, self.config.section_count),
        )
        return self._section_collection(sections)

    async def refresh_sections(
        self,
        user_id: UUID,
    ) -> RecommendationSectionCollection:
        refresh_lock = self._get_refresh_lock(user_id)
        if refresh_lock.locked():
            msg = "A recommendation refresh is already running for this user"
            raise RecommendationRefreshInProgressError(msg)
        await refresh_lock.acquire()
        try:
            return await self._refresh_sections_locked(user_id)
        finally:
            refresh_lock.release()
            self._remove_refresh_lock(user_id, refresh_lock)

    async def _refresh_sections_locked(
        self,
        user_id: UUID,
    ) -> RecommendationSectionCollection:
        self._require_enabled()
        mapping = await self._mapping_for_user(user_id, required=True)
        if mapping is None:
            msg = "No viewing-history mapping exists for this user"
            raise RecommendationConfigurationError(msg)
        source = self._select_source(mapping)
        started_at = utc_now()
        lease_id = uuid4()
        acquired = await self.repository.try_acquire_refresh_lease(
            user_id,
            source,
            lease_id=lease_id,
            started_at=started_at,
            expires_at=started_at
            + timedelta(seconds=self.config.refresh_lease_timeout_seconds),
        )
        if not acquired:
            msg = "A recommendation refresh is already running for this user"
            raise RecommendationRefreshInProgressError(msg)

        try:
            fresh_history = await self._fetch_history(mapping, source)
            await self._enrich_history(fresh_history, source)
            await self.repository.insert_history(
                [self._history_schema(user_id, item) for item in fresh_history]
            )
            history = await self.repository.get_recent_history(
                user_id,
                limit=self.config.max_history_items_per_sync,
            )
            if len(history) < self.config.minimum_history_items:
                msg = (
                    f"At least {self.config.minimum_history_items} history items are "
                    "required before generating recommendations"
                )
                raise RecommendationConfigurationError(msg)  # noqa: TRY301

            previous = await self.repository.list_previous_section_identities(user_id)
            exclusions = [
                *self._history_identities(history),
                *await self.repository.list_media_manager_library_identities(),
                *await self._library_inventory(source),
                *previous,
            ]
            sources = self._section_sources(history)[: self.config.section_count]
            log.info(
                "[Recommendations] Valid recommendation seed titles: %d; exclusions: %d",
                len(sources),
                len(exclusions),
            )
            sections = await self._generate_sections(
                user_id,
                sources,
                exclusions,
            )
            if not sections:
                msg = (
                    "No new recommendations remained after checking viewing history "
                    "and the complete Plex library. Existing recommendations were kept."
                )
                raise RecommendationProviderError(msg)  # noqa: TRY301

            log.info(
                "[Recommendations] Recommendation sections produced: %d", len(sections)
            )

            await self.repository.replace_sections(user_id, sections)
            completed_at = utc_now()
            cursor = (
                max(item.watched_at for item in fresh_history).isoformat()
                if fresh_history
                else None
            )
            await self.repository.mark_sync_success(
                user_id,
                source,
                cursor=cursor,
                completed_at=completed_at,
                generated_at=completed_at,
            )
            return self._section_collection(sections)
        except Exception as error:
            await self.repository.mark_sync_failure(
                user_id,
                source,
                self._safe_error(error),
            )
            raise
        finally:
            await self.repository.release_refresh_lease(user_id, source, lease_id)

    async def refresh_user(self, user_id: UUID) -> RecommendationRefreshResult:
        refresh_lock = self._get_refresh_lock(user_id)
        if refresh_lock.locked():
            msg = "A recommendation refresh is already running for this user"
            raise RecommendationRefreshInProgressError(msg)
        await refresh_lock.acquire()
        try:
            return await self._refresh_user_locked(user_id)
        finally:
            refresh_lock.release()
            self._remove_refresh_lock(user_id, refresh_lock)

    async def _refresh_user_locked(
        self,
        user_id: UUID,
    ) -> RecommendationRefreshResult:
        self._require_enabled()
        mapping = await self._mapping_for_user(user_id, required=True)
        if mapping is None:
            msg = "No viewing-history mapping exists for this user"
            raise RecommendationConfigurationError(msg)
        source = self._select_source(mapping)
        started_at = utc_now()
        lease_id = uuid4()
        lease_acquired = await self.repository.try_acquire_refresh_lease(
            user_id,
            source,
            lease_id=lease_id,
            started_at=started_at,
            expires_at=started_at
            + timedelta(seconds=self.config.refresh_lease_timeout_seconds),
        )
        if not lease_acquired:
            msg = "A recommendation refresh is already running for this user"
            raise RecommendationRefreshInProgressError(msg)
        try:
            source_items = await self._fetch_history(mapping, source)
            await self._enrich_history(source_items, source)
            history_items = [
                self._history_schema(user_id, source_item)
                for source_item in source_items
            ]
            inserted_count = await self.repository.insert_history(history_items)
            total_count = await self.repository.history_count(user_id)
            statistics = await self._fetch_statistics(mapping, source, source_items)

            generated_count = 0
            generated_at = None
            skipped_reason = None
            if total_count < self.config.minimum_history_items:
                skipped_reason = (
                    f"At least {self.config.minimum_history_items} history items are "
                    "required before generating recommendations"
                )
            else:
                generated_count = await self._generate_from_stored_history(
                    user_id,
                    statistics,
                )
                generated_at = utc_now()

            completed_at = utc_now()
            cursor = (
                max(item.watched_at for item in source_items).isoformat()
                if source_items
                else None
            )
            await self.repository.mark_sync_success(
                user_id,
                source,
                cursor=cursor,
                completed_at=completed_at,
                generated_at=generated_at,
            )
            return RecommendationRefreshResult(
                user_id=user_id,
                source=source,
                history_items_received=len(source_items),
                history_items_inserted=inserted_count,
                total_history_items=total_count,
                recommendations_generated=generated_count,
                started_at=started_at,
                completed_at=completed_at,
                skipped_reason=skipped_reason,
            )
        except Exception as error:
            await self.repository.mark_sync_failure(
                user_id,
                source,
                self._safe_error(error),
            )
            log.warning(
                "Recommendation refresh failed for user %s (%s)",
                user_id,
                type(error).__name__,
            )
            raise
        finally:
            await self.repository.release_refresh_lease(user_id, source, lease_id)

    async def refresh_all_users(self) -> list[RecommendationRefreshResult]:
        if not self.config.enabled:
            return []
        await self._persist_config_mappings()
        results: list[RecommendationRefreshResult] = []
        for mapping in await self.repository.list_enabled_mappings():
            try:
                results.append(await self.refresh_user(mapping.user_id))
            except RecommendationRefreshInProgressError:
                log.debug(
                    "Skipping concurrent recommendation refresh for user %s",
                    mapping.user_id,
                )
            except Exception:
                log.warning(
                    "Scheduled recommendation refresh failed for user %s",
                    mapping.user_id,
                )
        return results

    async def refresh_due_users(self) -> list[RecommendationRefreshResult]:
        """Refresh configured users only when their interval has elapsed."""
        if not self.config.enabled:
            return []
        await self._persist_config_mappings()
        due_before = utc_now() - timedelta(minutes=self.config.refresh_interval_minutes)
        results: list[RecommendationRefreshResult] = []
        for mapping in await self.repository.list_enabled_mappings():
            states = await self.repository.get_sync_states(mapping.user_id)
            latest_activity = max(
                (
                    timestamp
                    for state in states
                    for timestamp in (
                        state.last_generated_at,
                        state.last_sync_completed_at,
                    )
                    if timestamp is not None
                ),
                default=None,
            )
            if latest_activity is not None and latest_activity > due_before:
                continue
            try:
                results.append(await self.refresh_user(mapping.user_id))
            except RecommendationRefreshInProgressError:
                log.debug(
                    "Skipping due recommendation refresh already running for user %s",
                    mapping.user_id,
                )
            except Exception:
                log.warning(
                    "Due recommendation refresh failed for user %s",
                    mapping.user_id,
                )
        return results

    async def ingest_plex_webhook(
        self,
        payload: dict[str, object],
        supplied_secret: str | None,
    ) -> PlexWebhookResult:
        self._authenticate_webhook(supplied_secret)
        event = self.plex_client.parse_webhook(payload)
        if event is None:
            return PlexWebhookResult(
                accepted=False,
                reason="The Plex event is not a supported watch or rating event",
            )
        configured_server_id = self.config.plex.server_uuid
        if configured_server_id is not None and (
            event.server_id is None
            or event.server_id.casefold() != configured_server_id
        ):
            return PlexWebhookResult(
                accepted=False,
                reason="The Plex webhook originated from an unexpected server",
            )
        await self._persist_config_mappings()
        mapping = await self.repository.get_mapping_by_plex_identity(
            event.account_id,
            event.account_name,
        )
        if mapping is None:
            return PlexWebhookResult(
                accepted=False,
                reason="The Plex account is not mapped to a Media Manager user",
            )
        inserted = bool(
            await self.repository.insert_history(
                [self._history_schema(mapping.user_id, event.history_item)]
            )
        )
        refreshed = False
        if inserted and self.config.generate_on_webhook:
            total_count = await self.repository.history_count(mapping.user_id)
            if total_count >= self.config.minimum_history_items:
                await self._generate_from_stored_history(mapping.user_id, [])
                refreshed = True
                now = utc_now()
                await self.repository.mark_sync_success(
                    mapping.user_id,
                    HistorySource.PLEX,
                    cursor=event.history_item.watched_at.isoformat(),
                    completed_at=now,
                    generated_at=now,
                )
        return PlexWebhookResult(
            accepted=True,
            inserted=inserted,
            refreshed=refreshed,
        )

    def _require_enabled(self) -> None:
        if not self.config.enabled:
            msg = "Personal recommendations are disabled"
            raise RecommendationConfigurationError(msg)

    def authenticate_plex_webhook(self, supplied_secret: str | None) -> None:
        """Authenticate a webhook before its potentially large body is consumed."""
        self._authenticate_webhook(supplied_secret)

    async def _mapping_for_user(
        self,
        user_id: UUID,
        *,
        required: bool,
    ) -> RecommendationUserMappingSchema | None:
        config_mapping = self.config.mapping_for_user(user_id)
        if config_mapping is not None:
            mapping = await self._persist_mapping(config_mapping)
            if required and not mapping.enabled:
                msg = "Viewing-history recommendations are disabled for this user"
                raise RecommendationConfigurationError(msg)
            return mapping
        mapping = await self.repository.get_mapping(user_id)
        if required and (mapping is None or not mapping.enabled):
            msg = "No viewing-history mapping exists for this user"
            raise RecommendationConfigurationError(msg)
        return mapping

    async def _persist_config_mappings(self) -> None:
        for mapping in self.config.users:
            await self._persist_mapping(mapping)

    async def _persist_mapping(
        self,
        mapping: RecommendationUserMapping,
    ) -> RecommendationUserMappingSchema:
        return await self.repository.upsert_mapping(
            RecommendationUserMappingSchema(
                user_id=mapping.user_id,
                tautulli_user_id=mapping.tautulli_user_id,
                plex_account_id=mapping.plex_account_id,
                plex_username=mapping.plex_username,
                enabled=mapping.enabled,
            )
        )

    def _select_source(
        self,
        mapping: RecommendationUserMappingSchema,
    ) -> HistorySource:
        if self.config.history_provider == "tautulli":
            if not mapping.tautulli_user_id:
                msg = "The user has no Tautulli identity mapping"
                raise RecommendationConfigurationError(msg)
            return HistorySource.TAUTULLI
        if self.config.history_provider == "plex":
            if not mapping.plex_account_id:
                msg = "The user has no Plex account ID mapping"
                raise RecommendationConfigurationError(msg)
            return HistorySource.PLEX
        if self.config.tautulli.enabled and mapping.tautulli_user_id:
            return HistorySource.TAUTULLI
        if self.config.plex.enabled and mapping.plex_account_id:
            return HistorySource.PLEX
        msg = "No enabled history provider matches this user mapping"
        raise RecommendationConfigurationError(msg)

    async def _fetch_history(
        self,
        mapping: RecommendationUserMappingSchema,
        source: HistorySource,
    ) -> list[SourceHistoryItem]:
        page_size = self.config.history_page_size
        maximum = self.config.max_history_items_per_sync
        if source == HistorySource.PLEX:
            if not mapping.plex_account_id:
                return []
            playback_items: list[SourceHistoryItem] = []
            for start in range(0, maximum, page_size):
                request_size = min(page_size, maximum - start)
                page = await self.plex_client.get_history(
                    mapping.plex_account_id,
                    start=start,
                    size=request_size,
                )
                playback_items.extend(page)
                if len(page) < request_size:
                    break
            log.info("[Plex] Playback history records: %d", len(playback_items))
            watched_items = await self.plex_client.get_watched_library_history(
                mapping.plex_account_id,
                maximum=maximum,
            )
            merged = {
                item.source_event_id: item for item in [*playback_items, *watched_items]
            }
            items = sorted(
                merged.values(),
                key=lambda item: item.watched_at,
                reverse=True,
            )
            log.info("[Plex] Normalized history records: %d", len(items))
            return items[:maximum]

        items: list[SourceHistoryItem] = []
        for start in range(0, maximum, page_size):
            request_size = min(page_size, maximum - start)
            if not mapping.tautulli_user_id:
                break
            page = await self.tautulli_client.get_history(
                mapping.tautulli_user_id,
                start=start,
                length=request_size,
            )
            items.extend(page)
            if len(page) < request_size:
                break
        return items[:maximum]

    async def _fetch_statistics(
        self,
        mapping: RecommendationUserMappingSchema,
        source: HistorySource,
        source_items: list[SourceHistoryItem],
    ) -> list[SourceStatistic]:
        try:
            if source == HistorySource.TAUTULLI and mapping.tautulli_user_id:
                return await self.tautulli_client.get_statistics(
                    mapping.tautulli_user_id
                )
            return self._statistics_from_history(source_items)
        except RecommendationProviderError:
            log.warning("History statistics were unavailable; using history only")
            return []

    async def _enrich_history(
        self,
        items: list[SourceHistoryItem],
        source: HistorySource,
    ) -> None:
        if self.config.metadata_enrichment_limit == 0:
            return
        metadata_cache: dict[str, SourceMetadata] = {}
        enriched = 0
        for item in items:
            media_id = item.source_media_id
            if (
                enriched >= self.config.metadata_enrichment_limit
                or media_id is None
                or (item.genres and item.rating is not None)
            ):
                continue
            try:
                metadata = metadata_cache.get(media_id)
                if metadata is None:
                    if source == HistorySource.TAUTULLI:
                        metadata = await self.tautulli_client.get_metadata(media_id)
                    else:
                        metadata = await self.plex_client.get_metadata(media_id)
                    metadata_cache[media_id] = metadata
                    enriched += 1
                if not item.genres:
                    item.genres = metadata.genres
                if item.rating is None:
                    item.rating = metadata.rating
            except RecommendationProviderError:
                log.warning("Metadata enrichment failed for one history item")

    async def _library_inventory(
        self,
        source: HistorySource,
    ) -> list[LibraryMediaIdentity]:
        """Load the full library; failing closed prevents unsafe recommendations."""
        if self.config.plex.enabled and self.config.plex.token is not None:
            return await self.plex_client.get_library_inventory(
                cache_minutes=self.config.plex_library_cache_minutes
            )
        if self.config.tautulli.enabled and source is HistorySource.TAUTULLI:
            return await self.tautulli_client.get_library_inventory(
                cache_minutes=self.config.plex_library_cache_minutes
            )
        msg = (
            "A Plex or Tautulli library connection is required so existing titles "
            "can be excluded safely."
        )
        raise RecommendationConfigurationError(msg)

    @staticmethod
    def _history_identities(
        history: list[WatchHistoryItemSchema],
    ) -> list[LibraryMediaIdentity]:
        return [
            LibraryMediaIdentity(
                media_type=(
                    "show" if item.media_type in {"episode", "show"} else "movie"
                ),
                title=(
                    item.series_title
                    if item.media_type == "episode" and item.series_title
                    else item.title
                ),
                year=item.year if item.media_type != "episode" else None,
                external_ids=(
                    item.external_ids if item.media_type != "episode" else {}
                ),
            )
            for item in history
        ]

    @staticmethod
    def _section_sources(
        history: list[WatchHistoryItemSchema],
    ) -> list[RecommendationSource]:
        sources: dict[tuple[str, str], RecommendationSource] = {}
        for item in history:
            media_type = "show" if item.media_type in {"episode", "show"} else "movie"
            title = (
                item.series_title
                if item.media_type == "episode" and item.series_title
                else item.title
            )
            key = (media_type, normalized_title(title))
            existing = sources.get(key)
            if existing is None:
                sources[key] = RecommendationSource(
                    title=title,
                    media_type=media_type,
                    year=item.year if item.media_type != "episode" else None,
                    genres=item.genres,
                    rating=item.rating,
                    play_count=1,
                    external_ids=(
                        item.external_ids if item.media_type != "episode" else {}
                    ),
                    watched_at=item.watched_at,
                )
                continue
            existing.play_count += 1
            existing.genres = list(dict.fromkeys([*existing.genres, *item.genres]))[:20]
            if existing.rating is None and item.rating is not None:
                existing.rating = item.rating
            if item.watched_at > existing.watched_at:
                existing.watched_at = item.watched_at
            if not existing.external_ids and item.media_type != "episode":
                existing.external_ids = item.external_ids

        return sorted(
            sources.values(),
            key=lambda item: (
                item.rating if item.rating is not None else -1,
                item.play_count,
                item.watched_at,
            ),
            reverse=True,
        )

    async def _generate_sections(
        self,
        user_id: UUID,
        sources: list[RecommendationSource],
        exclusions: list[LibraryMediaIdentity],
    ) -> list[RecommendationSectionSchema]:
        semaphore = asyncio.Semaphore(self.config.section_fetch_concurrency)

        async def fetch(
            section_source: RecommendationSource,
        ) -> tuple[list[RecommendationCandidate], int]:
            async with semaphore:
                try:
                    return await self.recommendation_catalog.candidates_for_source(
                        section_source,
                        candidate_budget=self.config.section_candidate_budget,
                    )
                except RecommendationProviderError:
                    log.warning(
                        "Could not generate recommendation candidates for %s",
                        section_source.title,
                    )
                    return [], 0

        fetched = await asyncio.gather(*(fetch(source) for source in sources))
        external_keys, title_keys = self._identity_index(exclusions)
        page_external_keys: set[tuple[str, str, str]] = set()
        page_title_keys: set[tuple[str, str]] = set()
        generated_at = utc_now()
        expires_at = generated_at + timedelta(
            hours=self.config.recommendation_ttl_hours
        )
        sections: list[RecommendationSectionSchema] = []

        for section_source, (candidates, considered) in zip(
            sources,
            fetched,
            strict=True,
        ):
            items: list[RecommendationSectionItemSchema] = []
            for candidate in candidates:
                external_key = (
                    candidate.media_type,
                    "tmdb",
                    str(candidate.external_id),
                )
                title_key = (
                    candidate.media_type,
                    normalized_title(candidate.name),
                )
                if (
                    external_key in external_keys
                    or title_key in title_keys
                    or external_key in page_external_keys
                    or title_key in page_title_keys
                ):
                    continue
                page_external_keys.add(external_key)
                page_title_keys.add(title_key)
                items.append(
                    RecommendationSectionItemSchema(
                        section_id=uuid4(),
                        name=candidate.name,
                        media_type=RecommendationMediaType(candidate.media_type),
                        year=candidate.year,
                        external_id=candidate.external_id,
                        poster_path=candidate.poster_path,
                        score=self._candidate_score(candidate, len(items)),
                        rank=len(items) + 1,
                    )
                )
                if len(items) >= self.config.section_item_count:
                    break

            if not items:
                continue
            section_id = uuid4()
            for item in items:
                item.section_id = section_id
            sections.append(
                RecommendationSectionSchema(
                    section_id=section_id,
                    user_id=user_id,
                    source_title=section_source.title,
                    source_media_type=RecommendationMediaType(
                        section_source.media_type
                    ),
                    source_year=section_source.year,
                    source_external_ids=section_source.external_ids,
                    source_genres=section_source.genres,
                    reason=self._section_reason(section_source),
                    rank=len(sections) + 1,
                    candidates_considered=min(
                        considered,
                        self.config.section_candidate_budget,
                    ),
                    generated_at=generated_at,
                    expires_at=expires_at,
                    items=items,
                )
            )
            if len(sections) >= self.config.section_count:
                break
        return sections

    @staticmethod
    def _identity_index(
        identities: list[LibraryMediaIdentity],
    ) -> tuple[set[tuple[str, str, str]], set[tuple[str, str]]]:
        external: set[tuple[str, str, str]] = set()
        titles: set[tuple[str, str]] = set()
        for identity in identities:
            titles.add((identity.media_type, normalized_title(identity.title)))
            external.update(
                (
                    identity.media_type,
                    provider.casefold(),
                    str(external_id).strip().casefold(),
                )
                for provider, external_id in identity.external_ids.items()
                if str(external_id).strip()
            )
        return external, titles

    @staticmethod
    def _candidate_score(
        candidate: RecommendationCandidate,
        position: int,
    ) -> float:
        return max(
            0.0,
            (candidate.vote_average or 0)
            + min(candidate.popularity or 0, 200) / 200
            + max(0, 25 - position) / 100,
        )

    @staticmethod
    def _section_reason(source: RecommendationSource) -> str:
        if source.rating is not None:
            return f"Because you rated {source.title} {source.rating:g}/10."
        if source.play_count > 1:
            return f"Because you watched {source.title} {source.play_count} times."
        return f"Because you watched {source.title}."

    @staticmethod
    def _section_collection(
        sections: list[RecommendationSectionSchema],
    ) -> RecommendationSectionCollection:
        generated_at = max(
            (section.generated_at for section in sections),
            default=None,
        )
        return RecommendationSectionCollection(
            sections=sections,
            section_count=len(sections),
            item_count=sum(len(section.items) for section in sections),
            generated_at=generated_at,
        )

    async def _generate_from_stored_history(
        self,
        user_id: UUID,
        statistics: list[SourceStatistic],
    ) -> int:
        history = await self.repository.get_recent_history(
            user_id,
            limit=self.config.prompt_history_items,
        )
        profile = self._build_taste_profile(history, statistics)
        previous_recommendations = await self.repository.list_recommendations(
            user_id,
            limit=50,
            include_expired=True,
        )
        previous_keys = {
            (item.media_type.value, normalized_title(item.name))
            for item in previous_recommendations
        }
        request_count = min(
            50,
            self.config.recommendation_count + len(previous_keys),
        )
        batch = await self.ollama_client.generate_recommendations(
            profile,
            request_count,
            excluded_titles=[
                (media_type, title) for media_type, title in sorted(previous_keys)
            ],
        )
        generated_at = utc_now()
        expires_at = generated_at + timedelta(
            hours=self.config.recommendation_ttl_hours
        )
        watched = {
            (
                "show" if item.media_type in {"show", "episode"} else "movie",
                normalized_title(
                    item.series_title
                    if item.media_type == "episode" and item.series_title
                    else item.title
                ),
            )
            for item in history
        }
        seen: set[tuple[str, str]] = set()
        recommendations: list[RecommendationSchema] = []
        for generated in batch.recommendations:
            key = (generated.media_type, normalized_title(generated.title))
            if key in watched or key in seen or key in previous_keys:
                continue
            seen.add(key)
            metadata = (
                await self.metadata_resolver(generated)
                if self.metadata_resolver is not None
                else None
            )
            recommendations.append(
                RecommendationSchema(
                    user_id=user_id,
                    name=metadata.name if metadata is not None else generated.title,
                    media_type=RecommendationMediaType(generated.media_type),
                    year=(
                        metadata.year
                        if metadata is not None and metadata.year is not None
                        else generated.year
                    ),
                    external_id=(
                        metadata.external_id if metadata is not None else None
                    ),
                    metadata_provider=(
                        metadata.metadata_provider if metadata is not None else None
                    ),
                    poster_path=metadata.poster_path if metadata is not None else None,
                    vote_average=(
                        metadata.vote_average if metadata is not None else None
                    ),
                    overview=metadata.overview if metadata is not None else None,
                    added=metadata.added if metadata is not None else False,
                    media_id=metadata.id if metadata is not None else None,
                    reason=self._grounded_reason(generated, profile),
                    genres=generated.genres,
                    confidence=generated.confidence,
                    rank=len(recommendations) + 1,
                    model_name=self.config.ollama.model,
                    generated_at=generated_at,
                    expires_at=expires_at,
                )
            )
            if len(recommendations) >= self.config.recommendation_count:
                break
        if not recommendations:
            msg = (
                "The recommendation provider did not return any new, verifiable titles. "
                "Your existing recommendations were kept."
            )
            raise RecommendationProviderError(msg)
        await self.repository.replace_recommendations(user_id, recommendations)
        return len(recommendations)

    @staticmethod
    def _grounded_reason(
        generated: GeneratedRecommendation,
        profile: TasteProfile,
    ) -> str:
        """Build a reason from persisted history instead of trusting model prose."""
        generated_genres = {genre.casefold() for genre in generated.genres}
        matching_history = [
            entry
            for entry in profile.watched
            if generated_genres.intersection(genre.casefold() for genre in entry.genres)
        ]
        candidates = matching_history or profile.watched
        if not candidates:
            return "Selected from the genres and viewing patterns in your saved watch history."

        reference = max(
            candidates,
            key=lambda entry: (
                entry.rating if entry.rating is not None else -1,
                entry.play_count,
            ),
        )
        shared_genre = next(
            (
                genre
                for genre in reference.genres
                if genre.casefold() in generated_genres
            ),
            None,
        )

        if reference.rating is not None:
            return (
                f"Because you rated {reference.title} {reference.rating:g}/10"
                + (
                    f" and {shared_genre} appears in your history"
                    if shared_genre
                    else ""
                )
                + ", this may suit you."
            )
        if reference.play_count > 1:
            return (
                f"Because you watched {reference.title} {reference.play_count} times"
                + (
                    f" and {shared_genre} appears in your history"
                    if shared_genre
                    else ""
                )
                + ", this may suit you."
            )
        return (
            f"Because you watched {reference.title}"
            + (
                f" and {shared_genre} appears in your viewing history"
                if shared_genre
                else ""
            )
            + ", this may suit you."
        )

    @staticmethod
    def _history_schema(
        user_id: UUID,
        item: SourceHistoryItem,
    ) -> WatchHistoryItemSchema:
        return WatchHistoryItemSchema(
            user_id=user_id,
            source=item.source,
            source_event_id=item.source_event_id,
            event_type=item.event_type,
            media_type=item.media_type,
            title=item.title,
            series_title=item.series_title,
            year=item.year,
            genres=item.genres,
            rating=item.rating,
            watched_at=item.watched_at,
            watch_duration_seconds=item.watch_duration_seconds,
            completion_percent=item.completion_percent,
            external_ids=item.external_ids,
        )

    @staticmethod
    def _statistics_from_history(
        items: list[SourceHistoryItem],
    ) -> list[SourceStatistic]:
        counts: Counter[tuple[str, str]] = Counter()
        durations: Counter[tuple[str, str]] = Counter()
        for item in items:
            media_type = "show" if item.media_type in {"show", "episode"} else "movie"
            title = item.series_title if item.media_type == "episode" else item.title
            if not title:
                continue
            key = (media_type, title)
            counts[key] += 1
            durations[key] += item.watch_duration_seconds or 0
        return [
            SourceStatistic(
                category="play_history",
                title=title,
                media_type=media_type,
                play_count=count,
                duration_seconds=durations[(media_type, title)],
            )
            for (media_type, title), count in counts.most_common(20)
        ]

    @staticmethod
    def _build_taste_profile(
        history: list[WatchHistoryItemSchema],
        statistics: list[SourceStatistic],
    ) -> TasteProfile:
        entries: dict[tuple[str, str], TasteHistoryEntry] = {}
        genre_counts: Counter[str] = Counter()
        for item in history:
            media_type = "show" if item.media_type in {"show", "episode"} else "movie"
            title = (
                item.series_title
                if item.media_type == "episode" and item.series_title
                else item.title
            )
            key = (media_type, normalized_title(title))
            entry = entries.get(key)
            if entry is None:
                entry = TasteHistoryEntry(
                    title=title,
                    media_type=media_type,
                    year=item.year,
                    genres=item.genres,
                    rating=item.rating,
                )
                entries[key] = entry
            else:
                entry.play_count += 1
                entry.genres = list(dict.fromkeys([*entry.genres, *item.genres]))[:10]
                if entry.rating is None and item.rating is not None:
                    entry.rating = item.rating
            genre_counts.update(item.genres)
        return TasteProfile(
            watched=list(entries.values()),
            top_genres=[genre for genre, _count in genre_counts.most_common(15)],
            statistics=statistics[:50],
        )

    def _authenticate_webhook(self, supplied_secret: str | None) -> None:
        configured_secret = self.config.plex.webhook_secret
        if (
            not self.config.plex.webhook_enabled
            or configured_secret is None
            or supplied_secret is None
            or not compare_digest(
                configured_secret.get_secret_value().encode(),
                supplied_secret.encode(),
            )
        ):
            msg = "Plex webhook authentication failed"
            raise WebhookAuthenticationError(msg)

    @staticmethod
    def _safe_error(error: Exception) -> str:
        if isinstance(
            error,
            (RecommendationConfigurationError, RecommendationProviderError),
        ):
            return str(error)[:500]
        return f"Recommendation refresh failed ({type(error).__name__})"

    @classmethod
    def _get_refresh_lock(cls, user_id: UUID) -> asyncio.Lock:
        with cls._refresh_locks_guard:
            lock = cls._refresh_locks.get(user_id)
            if lock is None:
                lock = asyncio.Lock()
                cls._refresh_locks[user_id] = lock
            return lock

    @classmethod
    def _remove_refresh_lock(cls, user_id: UUID, lock: asyncio.Lock) -> None:
        with cls._refresh_locks_guard:
            if cls._refresh_locks.get(user_id) is lock:
                cls._refresh_locks.pop(user_id, None)
