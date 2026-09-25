import logging
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from media_manager.movies.models import Movie
from media_manager.recommendations.models import (
    MediaRecommendation,
    RecommendationSection,
    RecommendationSectionItem,
    RecommendationSyncState,
    RecommendationUserMapping,
    WatchHistoryItem,
)
from media_manager.recommendations.schemas import (
    HistorySource,
    LibraryMediaIdentity,
    RecommendationSchema,
    RecommendationSectionSchema,
    RecommendationUserMappingSchema,
    SyncStateSchema,
    WatchHistoryItemSchema,
    utc_now,
)
from media_manager.tv.models import Show

log = logging.getLogger(__name__)


class RecommendationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def upsert_mapping(
        self,
        mapping: RecommendationUserMappingSchema,
    ) -> RecommendationUserMappingSchema:
        db_mapping = await self.db.get(RecommendationUserMapping, mapping.user_id)
        if db_mapping is None:
            db_mapping = RecommendationUserMapping(
                user_id=mapping.user_id,
                tautulli_user_id=mapping.tautulli_user_id,
                plex_account_id=mapping.plex_account_id,
                plex_username=mapping.plex_username,
                enabled=mapping.enabled,
                created_at=mapping.created_at,
                updated_at=utc_now(),
            )
            self.db.add(db_mapping)
        else:
            db_mapping.tautulli_user_id = mapping.tautulli_user_id
            db_mapping.plex_account_id = mapping.plex_account_id
            db_mapping.plex_username = mapping.plex_username
            db_mapping.enabled = mapping.enabled
            db_mapping.updated_at = utc_now()
        try:
            await self.db.commit()
            await self.db.refresh(db_mapping)
        except IntegrityError as error:
            await self.db.rollback()
            msg = "An external history identity is already mapped to another user"
            raise ValueError(msg) from error
        return RecommendationUserMappingSchema.model_validate(db_mapping)

    async def get_mapping(
        self,
        user_id: UUID,
    ) -> RecommendationUserMappingSchema | None:
        db_mapping = await self.db.get(RecommendationUserMapping, user_id)
        if db_mapping is None:
            return None
        return RecommendationUserMappingSchema.model_validate(db_mapping)

    async def list_enabled_mappings(self) -> list[RecommendationUserMappingSchema]:
        statement = (
            select(RecommendationUserMapping)
            .where(RecommendationUserMapping.enabled.is_(True))
            .order_by(RecommendationUserMapping.user_id)
        )
        rows = (await self.db.execute(statement)).scalars().all()
        return [RecommendationUserMappingSchema.model_validate(row) for row in rows]

    async def get_mapping_by_plex_identity(
        self,
        account_id: str | None,
        username: str | None,
    ) -> RecommendationUserMappingSchema | None:
        if account_id:
            identity_condition = RecommendationUserMapping.plex_account_id == account_id
        elif username:
            identity_condition = RecommendationUserMapping.plex_username == username
        else:
            return None
        statement = select(RecommendationUserMapping).where(
            RecommendationUserMapping.enabled.is_(True),
            identity_condition,
        )
        db_mapping = (await self.db.execute(statement)).scalar_one_or_none()
        return (
            RecommendationUserMappingSchema.model_validate(db_mapping)
            if db_mapping is not None
            else None
        )

    async def insert_history(self, items: list[WatchHistoryItemSchema]) -> int:
        if not items:
            return 0
        values = [
            {
                "id": item.id,
                "user_id": item.user_id,
                "source": item.source.value,
                "source_event_id": item.source_event_id,
                "event_type": item.event_type.value,
                "media_type": item.media_type,
                "title": item.title,
                "series_title": item.series_title,
                "year": item.year,
                "genres": item.genres,
                "rating": item.rating,
                "watched_at": item.watched_at,
                "watch_duration_seconds": item.watch_duration_seconds,
                "completion_percent": item.completion_percent,
                "external_ids": item.external_ids,
                "created_at": item.created_at,
            }
            for item in items
        ]
        statement = (
            postgresql_insert(WatchHistoryItem)
            .values(values)
            .on_conflict_do_nothing(
                index_elements=["user_id", "source", "source_event_id"]
            )
            .returning(WatchHistoryItem.id)
        )
        try:
            inserted_ids = (await self.db.execute(statement)).scalars().all()
            await self.db.commit()
        except SQLAlchemyError:
            await self.db.rollback()
            log.exception("Could not persist privacy-minimized viewing history")
            raise
        return len(inserted_ids)

    async def get_recent_history(
        self,
        user_id: UUID,
        *,
        limit: int,
    ) -> list[WatchHistoryItemSchema]:
        statement = (
            select(WatchHistoryItem)
            .where(WatchHistoryItem.user_id == user_id)
            .order_by(WatchHistoryItem.watched_at.desc())
            .limit(limit)
        )
        rows = (await self.db.execute(statement)).scalars().all()
        return [WatchHistoryItemSchema.model_validate(row) for row in rows]

    async def history_count(self, user_id: UUID) -> int:
        statement = select(func.count(WatchHistoryItem.id)).where(
            WatchHistoryItem.user_id == user_id
        )
        return int((await self.db.execute(statement)).scalar_one())

    async def replace_recommendations(
        self,
        user_id: UUID,
        recommendations: list[RecommendationSchema],
    ) -> None:
        try:
            await self.db.execute(
                delete(MediaRecommendation).where(
                    MediaRecommendation.user_id == user_id
                )
            )
            self.db.add_all(
                [
                    MediaRecommendation(
                        id=recommendation.recommendation_id,
                        user_id=recommendation.user_id,
                        title=recommendation.name,
                        media_type=recommendation.media_type.value,
                        year=recommendation.year,
                        external_id=recommendation.external_id,
                        metadata_provider=recommendation.metadata_provider,
                        poster_path=recommendation.poster_path,
                        vote_average=recommendation.vote_average,
                        overview=recommendation.overview,
                        added=recommendation.added,
                        media_id=recommendation.media_id,
                        reason=recommendation.reason,
                        genres=recommendation.genres,
                        confidence=recommendation.confidence,
                        rank=recommendation.rank,
                        model_name=recommendation.model_name,
                        generated_at=recommendation.generated_at,
                        expires_at=recommendation.expires_at,
                    )
                    for recommendation in recommendations
                ]
            )
            await self.db.commit()
        except SQLAlchemyError:
            await self.db.rollback()
            log.exception("Could not replace generated recommendations")
            raise

    async def list_recommendations(
        self,
        user_id: UUID,
        *,
        limit: int,
        include_expired: bool = False,
    ) -> list[RecommendationSchema]:
        statement = select(MediaRecommendation).where(
            MediaRecommendation.user_id == user_id
        )
        if not include_expired:
            statement = statement.where(MediaRecommendation.expires_at > utc_now())
        statement = statement.order_by(MediaRecommendation.rank).limit(limit)
        rows = (await self.db.execute(statement)).scalars().all()
        return [RecommendationSchema.model_validate(row) for row in rows]

    async def recommendation_count(self, user_id: UUID) -> int:
        statement = select(func.count(MediaRecommendation.id)).where(
            MediaRecommendation.user_id == user_id,
            MediaRecommendation.expires_at > utc_now(),
        )
        return int((await self.db.execute(statement)).scalar_one())

    async def replace_sections(
        self,
        user_id: UUID,
        sections: list[RecommendationSectionSchema],
    ) -> None:
        try:
            await self.db.execute(
                delete(RecommendationSection).where(
                    RecommendationSection.user_id == user_id
                )
            )
            self.db.add_all(
                [
                    RecommendationSection(
                        id=section.section_id,
                        user_id=section.user_id,
                        source_title=section.source_title,
                        source_media_type=section.source_media_type.value,
                        source_year=section.source_year,
                        source_external_ids=section.source_external_ids,
                        source_genres=section.source_genres,
                        reason=section.reason,
                        rank=section.rank,
                        candidates_considered=section.candidates_considered,
                        generated_at=section.generated_at,
                        expires_at=section.expires_at,
                        items=[
                            RecommendationSectionItem(
                                id=item.recommendation_id,
                                section_id=section.section_id,
                                title=item.name,
                                media_type=item.media_type.value,
                                year=item.year,
                                external_id=item.external_id,
                                metadata_provider=item.metadata_provider,
                                poster_path=item.poster_path,
                                added=item.added,
                                media_id=item.media_id,
                                score=item.score,
                                rank=item.rank,
                            )
                            for item in section.items
                        ],
                    )
                    for section in sections
                ]
            )
            await self.db.commit()
        except SQLAlchemyError:
            await self.db.rollback()
            log.exception("Could not replace grouped recommendations")
            raise

    async def list_sections(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
        include_expired: bool = False,
    ) -> list[RecommendationSectionSchema]:
        statement = (
            select(RecommendationSection)
            .where(RecommendationSection.user_id == user_id)
            .options(selectinload(RecommendationSection.items))
        )
        if not include_expired:
            statement = statement.where(RecommendationSection.expires_at > utc_now())
        statement = statement.order_by(RecommendationSection.rank).limit(limit)
        rows = (await self.db.execute(statement)).scalars().unique().all()
        return [RecommendationSectionSchema.model_validate(row) for row in rows]

    async def list_previous_section_identities(
        self,
        user_id: UUID,
    ) -> list[LibraryMediaIdentity]:
        statement = (
            select(RecommendationSectionItem)
            .join(RecommendationSection)
            .where(RecommendationSection.user_id == user_id)
        )
        rows = (await self.db.execute(statement)).scalars().all()
        return [
            LibraryMediaIdentity(
                media_type="show" if row.media_type == "show" else "movie",
                title=row.title,
                year=row.year,
                external_ids={row.metadata_provider: str(row.external_id)},
            )
            for row in rows
        ]

    async def list_media_manager_library_identities(
        self,
    ) -> list[LibraryMediaIdentity]:
        movie_rows = (
            await self.db.execute(
                select(
                    Movie.name,
                    Movie.year,
                    Movie.external_id,
                    Movie.metadata_provider,
                    Movie.imdb_id,
                )
            )
        ).all()
        show_rows = (
            await self.db.execute(
                select(
                    Show.name,
                    Show.year,
                    Show.external_id,
                    Show.metadata_provider,
                    Show.imdb_id,
                )
            )
        ).all()

        def identity(row: object, media_type: str) -> LibraryMediaIdentity:
            name, year, external_id, provider, imdb_id = row  # type: ignore[misc]
            external_ids = {str(provider): str(external_id)}
            if imdb_id:
                external_ids["imdb"] = str(imdb_id)
            return LibraryMediaIdentity(
                media_type=media_type,  # type: ignore[arg-type]
                title=str(name),
                year=year,
                external_ids=external_ids,
            )

        return [
            *(identity(row, "movie") for row in movie_rows),
            *(identity(row, "show") for row in show_rows),
        ]

    async def get_sync_states(self, user_id: UUID) -> list[SyncStateSchema]:
        statement = (
            select(RecommendationSyncState)
            .where(RecommendationSyncState.user_id == user_id)
            .order_by(RecommendationSyncState.source)
        )
        rows = (await self.db.execute(statement)).scalars().all()
        return [SyncStateSchema.model_validate(row) for row in rows]

    async def try_acquire_refresh_lease(
        self,
        user_id: UUID,
        source: HistorySource,
        *,
        lease_id: UUID,
        started_at: datetime,
        expires_at: datetime,
    ) -> bool:
        """Atomically acquire a cross-worker refresh lease for one user/source."""
        try:
            await self._ensure_state(user_id, source)
            statement = (
                update(RecommendationSyncState)
                .where(
                    RecommendationSyncState.user_id == user_id,
                    RecommendationSyncState.source == source.value,
                    or_(
                        RecommendationSyncState.refresh_lease_expires_at.is_(None),
                        RecommendationSyncState.refresh_lease_expires_at <= started_at,
                    ),
                )
                .values(
                    refresh_lease_id=lease_id,
                    refresh_lease_expires_at=expires_at,
                    last_sync_started_at=started_at,
                    last_error=None,
                    updated_at=utc_now(),
                )
                .returning(RecommendationSyncState.id)
            )
            result = await self.db.execute(statement)
            acquired = result.scalar_one_or_none() is not None
            await self.db.commit()
        except SQLAlchemyError:
            await self.db.rollback()
            raise
        return acquired

    async def release_refresh_lease(
        self,
        user_id: UUID,
        source: HistorySource,
        lease_id: UUID,
    ) -> None:
        statement = (
            update(RecommendationSyncState)
            .where(
                RecommendationSyncState.user_id == user_id,
                RecommendationSyncState.source == source.value,
                RecommendationSyncState.refresh_lease_id == lease_id,
            )
            .values(
                refresh_lease_id=None,
                refresh_lease_expires_at=None,
                updated_at=utc_now(),
            )
        )
        try:
            await self.db.execute(statement)
            await self.db.commit()
        except SQLAlchemyError:
            await self.db.rollback()
            raise

    async def mark_sync_started(
        self,
        user_id: UUID,
        source: HistorySource,
        started_at: datetime,
    ) -> None:
        state = await self._get_or_create_state(user_id, source)
        state.last_sync_started_at = started_at
        state.last_error = None
        state.updated_at = utc_now()
        await self.db.commit()

    async def mark_sync_success(
        self,
        user_id: UUID,
        source: HistorySource,
        *,
        cursor: str | None,
        completed_at: datetime,
        generated_at: datetime | None,
    ) -> None:
        state = await self._get_or_create_state(user_id, source)
        state.last_cursor = cursor or state.last_cursor
        state.last_sync_completed_at = completed_at
        if generated_at is not None:
            state.last_generated_at = generated_at
        state.last_error = None
        state.updated_at = utc_now()
        await self.db.commit()

    async def mark_sync_failure(
        self,
        user_id: UUID,
        source: HistorySource,
        error_message: str,
    ) -> None:
        state = await self._get_or_create_state(user_id, source)
        state.last_error = error_message[:500]
        state.updated_at = utc_now()
        await self.db.commit()

    async def _get_or_create_state(
        self,
        user_id: UUID,
        source: HistorySource,
    ) -> RecommendationSyncState:
        await self._ensure_state(user_id, source)
        statement = select(RecommendationSyncState).where(
            RecommendationSyncState.user_id == user_id,
            RecommendationSyncState.source == source.value,
        )
        state = (await self.db.execute(statement)).scalar_one_or_none()
        if state is None:
            msg = "Could not create recommendation sync state"
            raise RuntimeError(msg)
        return state

    async def _ensure_state(
        self,
        user_id: UUID,
        source: HistorySource,
    ) -> None:
        statement = (
            postgresql_insert(RecommendationSyncState)
            .values(
                id=uuid4(),
                user_id=user_id,
                source=source.value,
                updated_at=utc_now(),
            )
            .on_conflict_do_nothing(index_elements=["user_id", "source"])
        )
        await self.db.execute(statement)
