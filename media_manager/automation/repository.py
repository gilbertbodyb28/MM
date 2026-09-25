from datetime import UTC, datetime, timedelta

from sqlalchemy import case, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from media_manager.automation.models import AutomationJob as AutomationJobModel
from media_manager.automation.schemas import (
    ACTIVE_AUTOMATION_STATUSES,
    RUNNABLE_AUTOMATION_STATUSES,
    TERMINAL_AUTOMATION_STATUSES,
    AutomationJob,
    AutomationJobId,
    AutomationJobKind,
    AutomationJobStatus,
)
from media_manager.exceptions import NotFoundError
from media_manager.indexer.schemas import IndexerQueryResult
from media_manager.movies.schemas import MovieId
from media_manager.torrent.schemas import Torrent
from media_manager.tv.schemas import EpisodeId, ShowId


def utc_now() -> datetime:
    return datetime.now(UTC)


class AutomationRepository:
    """Persistence and atomic job claiming for the automation pipeline."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_job(self, job_id: AutomationJobId) -> AutomationJob:
        db_job = await self.db.get(AutomationJobModel, job_id)
        if db_job is None:
            msg = f"Automation job with id {job_id} not found."
            raise NotFoundError(msg)
        return AutomationJob.model_validate(db_job)

    async def list_jobs(
        self,
        *,
        status: AutomationJobStatus | None = None,
        kind: AutomationJobKind | None = None,
        show_id: ShowId | None = None,
        episode_id: EpisodeId | None = None,
        limit: int = 100,
    ) -> list[AutomationJob]:
        stmt = select(AutomationJobModel)
        if status is not None:
            stmt = stmt.where(AutomationJobModel.status == status.value)
        if kind is not None:
            stmt = stmt.where(AutomationJobModel.kind == kind.value)
        if show_id is not None:
            stmt = stmt.where(AutomationJobModel.show_id == show_id)
        if episode_id is not None:
            stmt = stmt.where(AutomationJobModel.episode_id == episode_id)
        stmt = stmt.order_by(AutomationJobModel.created_at.desc()).limit(limit)
        results = (await self.db.execute(stmt)).scalars().all()
        return [AutomationJob.model_validate(job) for job in results]

    async def get_pending_show_targets(
        self,
        show_id: ShowId,
    ) -> tuple[set[EpisodeId], bool]:
        """Return queued episode jobs and whether a show job is running now.

        Other components use this to avoid searching for an episode that the
        automation queue already owns.
        """
        stmt = select(
            AutomationJobModel.kind,
            AutomationJobModel.status,
            AutomationJobModel.episode_id,
        ).where(
            AutomationJobModel.show_id == show_id,
            AutomationJobModel.status.not_in(
                [status.value for status in TERMINAL_AUTOMATION_STATUSES]
            ),
        )
        episode_ids: set[EpisodeId] = set()
        show_job_active = False
        for kind, status, episode_id in (await self.db.execute(stmt)).all():
            if kind == AutomationJobKind.episode.value and episode_id is not None:
                episode_ids.add(EpisodeId(episode_id))
            elif (
                kind == AutomationJobKind.show.value
                and AutomationJobStatus(status) in ACTIVE_AUTOMATION_STATUSES
            ):
                show_job_active = True
        return episode_ids, show_job_active

    async def enqueue_movie(
        self,
        movie_id: MovieId,
        *,
        force: bool = False,
        now: datetime | None = None,
    ) -> tuple[AutomationJob, bool]:
        return await self._enqueue(
            job_key=f"movie:{movie_id}",
            kind=AutomationJobKind.movie,
            movie_id=movie_id,
            show_id=None,
            episode_id=None,
            force=force,
            now=now,
        )

    async def enqueue_show(
        self,
        show_id: ShowId,
        *,
        force: bool = False,
        now: datetime | None = None,
    ) -> tuple[AutomationJob, bool]:
        return await self._enqueue(
            job_key=f"show:{show_id}",
            kind=AutomationJobKind.show,
            movie_id=None,
            show_id=show_id,
            episode_id=None,
            force=force,
            now=now,
        )

    async def enqueue_episode(
        self,
        show_id: ShowId,
        episode_id: EpisodeId,
        *,
        force: bool = False,
        now: datetime | None = None,
    ) -> tuple[AutomationJob, bool]:
        return await self._enqueue(
            job_key=f"episode:{episode_id}",
            kind=AutomationJobKind.episode,
            movie_id=None,
            show_id=show_id,
            episode_id=episode_id,
            force=force,
            now=now,
        )

    async def _enqueue(
        self,
        *,
        job_key: str,
        kind: AutomationJobKind,
        movie_id: MovieId | None,
        show_id: ShowId | None,
        episode_id: EpisodeId | None,
        force: bool,
        now: datetime | None,
    ) -> tuple[AutomationJob, bool]:
        current_time = now or utc_now()
        stmt = (
            select(AutomationJobModel)
            .where(AutomationJobModel.job_key == job_key)
            .with_for_update()
        )
        db_job = (await self.db.execute(stmt)).scalar_one_or_none()

        if db_job is not None:
            status = AutomationJobStatus(db_job.status)
            retry_cooldown_elapsed = (
                status != AutomationJobStatus.failed
                or db_job.next_attempt_at <= current_time
            )
            should_reset = status not in ACTIVE_AUTOMATION_STATUSES and (
                force
                or (status in TERMINAL_AUTOMATION_STATUSES and retry_cooldown_elapsed)
            )
            if should_reset:
                self._reset_job(db_job, current_time)
                await self.db.commit()
            return AutomationJob.model_validate(db_job), should_reset

        db_job = AutomationJobModel(
            job_key=job_key,
            kind=kind.value,
            status=AutomationJobStatus.queued.value,
            movie_id=movie_id,
            show_id=show_id,
            episode_id=episode_id,
            next_attempt_at=current_time,
            created_at=current_time,
            updated_at=current_time,
        )
        self.db.add(db_job)
        try:
            await self.db.commit()
            await self.db.refresh(db_job)
        except IntegrityError:
            # Another request inserted the same unique job key. The winner is
            # returned so callers still get an idempotent enqueue operation.
            await self.db.rollback()
            existing = (
                await self.db.execute(
                    select(AutomationJobModel).where(
                        AutomationJobModel.job_key == job_key
                    )
                )
            ).scalar_one()
            return AutomationJob.model_validate(existing), False
        return AutomationJob.model_validate(db_job), True

    async def claim_due_jobs(
        self,
        *,
        limit: int,
        lease_timeout_seconds: int,
        kinds: frozenset[AutomationJobKind] | None = None,
        now: datetime | None = None,
    ) -> list[AutomationJob]:
        current_time = now or utc_now()
        stale_before = current_time - timedelta(seconds=lease_timeout_seconds)

        stale_jobs = update(AutomationJobModel).where(
            AutomationJobModel.status.in_(
                [status.value for status in ACTIVE_AUTOMATION_STATUSES]
            ),
            AutomationJobModel.locked_at < stale_before,
        )
        if kinds is not None:
            stale_jobs = stale_jobs.where(
                AutomationJobModel.kind.in_([kind.value for kind in kinds])
            )
        await self.db.execute(
            stale_jobs
            .values(
                status=AutomationJobStatus.retry_wait.value,
                status_message="Recovered an expired worker lease.",
                last_error="The previous worker did not finish before its lease expired.",
                next_attempt_at=current_time,
                locked_at=None,
                updated_at=current_time,
            )
        )

        stmt = (
            select(AutomationJobModel)
            .where(
                AutomationJobModel.status.in_(
                    [status.value for status in RUNNABLE_AUTOMATION_STATUSES]
                ),
                AutomationJobModel.next_attempt_at <= current_time,
            )
        )
        if kinds is not None:
            stmt = stmt.where(
                AutomationJobModel.kind.in_([kind.value for kind in kinds])
            )
        stmt = (
            stmt.order_by(
                case(
                    (
                        AutomationJobModel.kind == AutomationJobKind.episode.value,
                        0,
                    ),
                    else_=1,
                ),
                AutomationJobModel.next_attempt_at,
                AutomationJobModel.created_at,
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        db_jobs = (await self.db.execute(stmt)).scalars().all()

        for db_job in db_jobs:
            db_job.status = AutomationJobStatus.searching.value
            db_job.status_message = "Searching configured indexers."
            db_job.attempts += 1
            db_job.locked_at = current_time
            db_job.started_at = current_time
            db_job.completed_at = None
            db_job.updated_at = current_time

        await self.db.commit()
        return [AutomationJob.model_validate(job) for job in db_jobs]

    async def mark_downloading(
        self,
        job_id: AutomationJobId,
        *,
        result: IndexerQueryResult,
        torrent: Torrent | None = None,
        message: str | None = None,
        now: datetime | None = None,
    ) -> AutomationJob:
        current_time = now or utc_now()
        db_job = await self._get_job_for_update(job_id)
        db_job.status = AutomationJobStatus.downloading.value
        db_job.status_message = (
            message or f"Submitted {result.title} to the download client."
        )
        db_job.selected_result_id = result.id
        db_job.selected_release_title = result.title
        if torrent is not None:
            db_job.torrent_id = torrent.id
        db_job.locked_at = current_time
        db_job.updated_at = current_time
        await self.db.commit()
        return AutomationJob.model_validate(db_job)

    async def mark_succeeded(
        self,
        job_id: AutomationJobId,
        *,
        message: str,
        now: datetime | None = None,
    ) -> AutomationJob:
        return await self._mark_terminal(
            job_id,
            status=AutomationJobStatus.succeeded,
            message=message,
            last_error=None,
            now=now,
        )

    async def mark_skipped(
        self,
        job_id: AutomationJobId,
        *,
        message: str,
        now: datetime | None = None,
    ) -> AutomationJob:
        return await self._mark_terminal(
            job_id,
            status=AutomationJobStatus.skipped,
            message=message,
            last_error=None,
            now=now,
        )

    async def mark_retry_or_failed(
        self,
        job_id: AutomationJobId,
        *,
        error: str,
        max_attempts: int,
        retry_at: datetime,
        exhausted_retry_at: datetime,
        now: datetime | None = None,
    ) -> AutomationJob:
        current_time = now or utc_now()
        db_job = await self._get_job_for_update(job_id)
        exhausted = db_job.attempts >= max_attempts
        db_job.status = (
            AutomationJobStatus.failed.value
            if exhausted
            else AutomationJobStatus.retry_wait.value
        )
        db_job.status_message = (
            "Retry limit reached; waiting for the next rescan window."
            if exhausted
            else f"Retry scheduled after attempt {db_job.attempts}."
        )
        db_job.last_error = error
        db_job.next_attempt_at = exhausted_retry_at if exhausted else retry_at
        db_job.locked_at = None
        db_job.updated_at = current_time
        db_job.completed_at = current_time if exhausted else None
        await self.db.commit()
        return AutomationJob.model_validate(db_job)

    async def retry_job(
        self,
        job_id: AutomationJobId,
        *,
        now: datetime | None = None,
    ) -> AutomationJob:
        current_time = now or utc_now()
        db_job = await self._get_job_for_update(job_id)
        if AutomationJobStatus(db_job.status) in ACTIVE_AUTOMATION_STATUSES:
            return AutomationJob.model_validate(db_job)
        self._reset_job(db_job, current_time)
        await self.db.commit()
        return AutomationJob.model_validate(db_job)

    async def _mark_terminal(
        self,
        job_id: AutomationJobId,
        *,
        status: AutomationJobStatus,
        message: str,
        last_error: str | None,
        now: datetime | None,
    ) -> AutomationJob:
        current_time = now or utc_now()
        db_job = await self._get_job_for_update(job_id)
        db_job.status = status.value
        db_job.status_message = message
        db_job.last_error = last_error
        db_job.completed_at = current_time
        db_job.locked_at = None
        db_job.updated_at = current_time
        await self.db.commit()
        return AutomationJob.model_validate(db_job)

    async def _get_job_for_update(self, job_id: AutomationJobId) -> AutomationJobModel:
        stmt = (
            select(AutomationJobModel)
            .where(AutomationJobModel.id == job_id)
            .with_for_update()
        )
        db_job = (await self.db.execute(stmt)).scalar_one_or_none()
        if db_job is None:
            msg = f"Automation job with id {job_id} not found."
            raise NotFoundError(msg)
        return db_job

    @staticmethod
    def _reset_job(db_job: AutomationJobModel, current_time: datetime) -> None:
        db_job.status = AutomationJobStatus.queued.value
        db_job.status_message = "Queued for automatic processing."
        db_job.attempts = 0
        db_job.next_attempt_at = current_time
        db_job.last_error = None
        db_job.selected_result_id = None
        db_job.selected_release_title = None
        db_job.torrent_id = None
        db_job.started_at = None
        db_job.completed_at = None
        db_job.locked_at = None
        db_job.updated_at = current_time
