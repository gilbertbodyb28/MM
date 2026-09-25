import typing
import uuid
from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from media_manager.tv.schemas import EpisodeId, ShowId

EpisodeScanRunId = typing.NewType("EpisodeScanRunId", UUID)
EpisodeScanItemId = typing.NewType("EpisodeScanItemId", UUID)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class EpisodeScanTrigger(StrEnum):
    scheduled = "scheduled"
    manual = "manual"


class EpisodeScanRunStatus(StrEnum):
    running = "running"
    succeeded = "succeeded"
    completed_with_errors = "completed_with_errors"
    failed = "failed"
    interrupted = "interrupted"


class EpisodeScanOutcome(StrEnum):
    sent = "sent"
    skipped = "skipped"
    not_found = "not_found"
    error = "error"


class EpisodeScanReason(StrEnum):
    # Skip reasons: the episode already has, or must not get, a download.
    in_library = "in_library"
    downloading = "downloading"
    queued = "queued"
    in_download_client = "in_download_client"
    not_monitored = "not_monitored"
    season_not_monitored = "season_not_monitored"
    # Error reasons.
    configuration = "configuration"
    search = "search"
    download = "download"
    unexpected = "unexpected"


class EpisodeScanSettings(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enabled: bool
    updated_at: datetime


class EpisodeScanSettingsUpdate(BaseModel):
    enabled: bool


class EpisodeScanRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: EpisodeScanRunId
    trigger: EpisodeScanTrigger
    status: EpisodeScanRunStatus
    started_at: datetime
    heartbeat_at: datetime
    finished_at: datetime | None = None
    shows_total: int = 0
    shows_checked: int = 0
    shows_failed: int = 0
    episodes_found: int = 0
    episodes_sent: int = 0
    episodes_skipped: int = 0
    episodes_not_found: int = 0
    errors: int = 0
    message: str | None = None


class EpisodeScanItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: EpisodeScanItemId = Field(
        default_factory=lambda: EpisodeScanItemId(uuid.uuid4())
    )
    run_id: EpisodeScanRunId
    show_id: ShowId | None = None
    episode_id: EpisodeId | None = None
    show_name: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    episode_title: str | None = None
    air_date: date | None = None
    outcome: EpisodeScanOutcome
    reason: EpisodeScanReason | None = None
    release_title: str | None = None
    indexer: str | None = None
    message: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)


class EpisodeScanProgress(BaseModel):
    """Counters a running scan periodically writes back to its run row."""

    shows_total: int = 0
    shows_checked: int = 0
    shows_failed: int = 0
    episodes_found: int = 0
    episodes_sent: int = 0
    episodes_skipped: int = 0
    episodes_not_found: int = 0
    errors: int = 0

    def record(self, outcome: EpisodeScanOutcome, *, episode: bool) -> None:
        if outcome == EpisodeScanOutcome.error:
            self.errors += 1
        if not episode:
            return
        self.episodes_found += 1
        if outcome == EpisodeScanOutcome.sent:
            self.episodes_sent += 1
        elif outcome == EpisodeScanOutcome.skipped:
            self.episodes_skipped += 1
        elif outcome == EpisodeScanOutcome.not_found:
            self.episodes_not_found += 1


class EpisodeScanStatus(BaseModel):
    enabled: bool
    interval_minutes: int
    lookback_days: int
    running: bool
    next_scan_at: datetime | None
    server_time: datetime
    latest_run: EpisodeScanRun | None = None
    latest_items: list[EpisodeScanItem] = Field(default_factory=list)
    recent_sent: list[EpisodeScanItem] = Field(default_factory=list)
    recent_runs: list[EpisodeScanRun] = Field(default_factory=list)
