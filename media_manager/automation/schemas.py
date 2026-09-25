import typing
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from media_manager.indexer.schemas import IndexerQueryResultId
from media_manager.movies.schemas import MovieId
from media_manager.torrent.schemas import TorrentId
from media_manager.tv.schemas import EpisodeId, ShowId

AutomationJobId = typing.NewType("AutomationJobId", UUID)


class AutomationJobKind(StrEnum):
    movie = "movie"
    show = "show"
    episode = "episode"


class AutomationJobStatus(StrEnum):
    queued = "queued"
    searching = "searching"
    downloading = "downloading"
    retry_wait = "retry_wait"
    succeeded = "succeeded"
    skipped = "skipped"
    failed = "failed"


ACTIVE_AUTOMATION_STATUSES = frozenset(
    {
        AutomationJobStatus.searching,
        AutomationJobStatus.downloading,
    }
)
RUNNABLE_AUTOMATION_STATUSES = frozenset(
    {
        AutomationJobStatus.queued,
        AutomationJobStatus.retry_wait,
    }
)
TERMINAL_AUTOMATION_STATUSES = frozenset(
    {
        AutomationJobStatus.succeeded,
        AutomationJobStatus.skipped,
        AutomationJobStatus.failed,
    }
)


class AutomationJob(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: AutomationJobId
    job_key: str
    kind: AutomationJobKind
    status: AutomationJobStatus
    movie_id: MovieId | None = None
    show_id: ShowId | None = None
    episode_id: EpisodeId | None = None
    attempts: int = 0
    next_attempt_at: datetime
    status_message: str | None = None
    last_error: str | None = None
    selected_result_id: IndexerQueryResultId | None = None
    selected_release_title: str | None = None
    torrent_id: TorrentId | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    locked_at: datetime | None = None


class AutomationCycleResult(BaseModel):
    queued: int = 0
    claimed: int = 0
    succeeded: int = 0
    skipped: int = 0
    retrying: int = 0
    failed: int = 0
    job_ids: list[AutomationJobId] = Field(default_factory=list)
