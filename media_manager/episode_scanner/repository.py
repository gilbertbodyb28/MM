from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from media_manager.episode_scanner.models import EpisodeScanItem as EpisodeScanItemModel
from media_manager.episode_scanner.models import EpisodeScanRun as EpisodeScanRunModel
from media_manager.episode_scanner.models import (
    EpisodeScanSettings as EpisodeScanSettingsModel,
)
from media_manager.episode_scanner.schemas import (
    EpisodeScanItem,
    EpisodeScanOutcome,
    EpisodeScanProgress,
    EpisodeScanRun,
    EpisodeScanRunId,
    EpisodeScanRunStatus,
    EpisodeScanSettings,
    EpisodeScanTrigger,
)
from media_manager.exceptions import NotFoundError

SETTINGS_ROW_ID = 1


def utc_now() -> datetime:
    return datetime.now(UTC)


class EpisodeScanRepository:
    """Persistence for the scanner toggle, scan runs and their results."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def rollback(self) -> None:
        """Discard a failed transaction so the next show can still be scanned."""
        await self.db.rollback()

    async def get_settings(self) -> EpisodeScanSettings:
        db_settings = await self.db.get(EpisodeScanSettingsModel, SETTINGS_ROW_ID)
        if db_settings is None:
            # The migration seeds this row; recreate it if it was removed.
            db_settings = EpisodeScanSettingsModel(id=SETTINGS_ROW_ID, enabled=True)
            self.db.add(db_settings)
            try:
                await self.db.commit()
            except IntegrityError:
                await self.db.rollback()
                db_settings = await self.db.get(
                    EpisodeScanSettingsModel, SETTINGS_ROW_ID
                )
                if db_settings is None:
                    raise
        return EpisodeScanSettings.model_validate(db_settings)

    async def set_enabled(self, enabled: bool) -> EpisodeScanSettings:
        await self.get_settings()
        db_settings = await self.db.get(EpisodeScanSettingsModel, SETTINGS_ROW_ID)
        if db_settings is None:
            msg = "Episode scanner settings are missing."
            raise NotFoundError(msg)
        db_settings.enabled = enabled
        db_settings.updated_at = utc_now()
        await self.db.commit()
        return EpisodeScanSettings.model_validate(db_settings)

    async def recover_stale_runs(
        self,
        *,
        lease_timeout_seconds: int,
        now: datetime | None = None,
    ) -> int:
        """Mark running scans without recent progress as interrupted."""
        current_time = now or utc_now()
        stale_before = current_time - timedelta(seconds=lease_timeout_seconds)
        result = await self.db.execute(
            update(EpisodeScanRunModel)
            .where(
                EpisodeScanRunModel.status == EpisodeScanRunStatus.running.value,
                EpisodeScanRunModel.heartbeat_at < stale_before,
            )
            .values(
                status=EpisodeScanRunStatus.interrupted.value,
                finished_at=current_time,
                message=(
                    "Scanningen slutade rapportera framsteg, till exempel för att "
                    "MediaManager startades om."
                ),
            )
        )
        await self.db.commit()
        return getattr(result, "rowcount", 0) or 0

    async def create_run(
        self,
        trigger: EpisodeScanTrigger,
        *,
        now: datetime | None = None,
    ) -> EpisodeScanRun | None:
        """Start a run, or return None when another scan is already running."""
        current_time = now or utc_now()
        db_run = EpisodeScanRunModel(
            trigger=trigger.value,
            status=EpisodeScanRunStatus.running.value,
            started_at=current_time,
            heartbeat_at=current_time,
        )
        self.db.add(db_run)
        try:
            await self.db.commit()
        except IntegrityError:
            # uq_episode_scan_run_single_running rejected a second running scan.
            await self.db.rollback()
            return None
        await self.db.refresh(db_run)
        return EpisodeScanRun.model_validate(db_run)

    async def get_run(self, run_id: EpisodeScanRunId) -> EpisodeScanRun:
        db_run = await self.db.get(EpisodeScanRunModel, run_id)
        if db_run is None:
            msg = f"Episode scan {run_id} not found."
            raise NotFoundError(msg)
        return EpisodeScanRun.model_validate(db_run)

    async def get_running_run(self) -> EpisodeScanRun | None:
        stmt = select(EpisodeScanRunModel).where(
            EpisodeScanRunModel.status == EpisodeScanRunStatus.running.value
        )
        db_run = (await self.db.execute(stmt)).scalars().first()
        return EpisodeScanRun.model_validate(db_run) if db_run is not None else None

    async def list_runs(self, *, limit: int = 10) -> list[EpisodeScanRun]:
        stmt = (
            select(EpisodeScanRunModel)
            .order_by(EpisodeScanRunModel.started_at.desc())
            .limit(limit)
        )
        results = (await self.db.execute(stmt)).scalars().all()
        return [EpisodeScanRun.model_validate(run) for run in results]

    async def get_latest_run(self) -> EpisodeScanRun | None:
        runs = await self.list_runs(limit=1)
        return runs[0] if runs else None

    async def touch_run(
        self,
        run_id: EpisodeScanRunId,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Renew a running scan's lease; False once it is no longer running."""
        result = await self.db.execute(
            update(EpisodeScanRunModel)
            .where(
                EpisodeScanRunModel.id == run_id,
                EpisodeScanRunModel.status == EpisodeScanRunStatus.running.value,
            )
            .values(heartbeat_at=now or utc_now())
        )
        await self.db.commit()
        return bool(getattr(result, "rowcount", 0))

    async def save_progress(
        self,
        run_id: EpisodeScanRunId,
        progress: EpisodeScanProgress,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Persist counters and renew the lease; False once no longer running."""
        result = await self.db.execute(
            update(EpisodeScanRunModel)
            .where(
                EpisodeScanRunModel.id == run_id,
                EpisodeScanRunModel.status == EpisodeScanRunStatus.running.value,
            )
            .values(heartbeat_at=now or utc_now(), **progress.model_dump())
        )
        await self.db.commit()
        return bool(getattr(result, "rowcount", 0))

    async def finish_run(
        self,
        run_id: EpisodeScanRunId,
        *,
        status: EpisodeScanRunStatus,
        progress: EpisodeScanProgress,
        message: str | None,
        now: datetime | None = None,
    ) -> EpisodeScanRun:
        current_time = now or utc_now()
        # Only a running scan can finish; one already marked as interrupted keeps
        # that status so a late worker cannot overwrite what the page showed.
        await self.db.execute(
            update(EpisodeScanRunModel)
            .where(
                EpisodeScanRunModel.id == run_id,
                EpisodeScanRunModel.status == EpisodeScanRunStatus.running.value,
            )
            .values(
                status=status.value,
                finished_at=current_time,
                heartbeat_at=current_time,
                message=message,
                **progress.model_dump(),
            )
        )
        await self.db.commit()
        return await self.get_run(run_id)

    async def add_item(self, item: EpisodeScanItem) -> EpisodeScanItem:
        db_item = EpisodeScanItemModel(
            **item.model_dump(exclude={"outcome", "reason"}),
            outcome=item.outcome.value,
            reason=item.reason.value if item.reason is not None else None,
        )
        self.db.add(db_item)
        await self.db.commit()
        return item

    async def list_items(
        self,
        run_id: EpisodeScanRunId,
        *,
        limit: int = 500,
    ) -> list[EpisodeScanItem]:
        stmt = (
            select(EpisodeScanItemModel)
            .where(EpisodeScanItemModel.run_id == run_id)
            .order_by(EpisodeScanItemModel.created_at, EpisodeScanItemModel.id)
            .limit(limit)
        )
        results = (await self.db.execute(stmt)).scalars().all()
        return [EpisodeScanItem.model_validate(item) for item in results]

    async def list_recent_items(
        self,
        outcome: EpisodeScanOutcome,
        *,
        limit: int = 25,
    ) -> list[EpisodeScanItem]:
        stmt = (
            select(EpisodeScanItemModel)
            .where(EpisodeScanItemModel.outcome == outcome.value)
            .order_by(EpisodeScanItemModel.created_at.desc())
            .limit(limit)
        )
        results = (await self.db.execute(stmt)).scalars().all()
        return [EpisodeScanItem.model_validate(item) for item in results]

    async def delete_runs_started_before(self, cutoff: datetime) -> int:
        result = await self.db.execute(
            delete(EpisodeScanRunModel).where(
                EpisodeScanRunModel.started_at < cutoff,
                EpisodeScanRunModel.status != EpisodeScanRunStatus.running.value,
            )
        )
        await self.db.commit()
        return getattr(result, "rowcount", 0) or 0
