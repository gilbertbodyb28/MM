# ruff: noqa: S101

import asyncio
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from media_manager.automation.repository import AutomationRepository
from media_manager.downloads.qbittorrent import QbittorrentGateway
from media_manager.episode_scanner.config import EpisodeScannerConfig
from media_manager.episode_scanner.repository import EpisodeScanRepository
from media_manager.episode_scanner.schemas import (
    EpisodeScanItem,
    EpisodeScanOutcome,
    EpisodeScanProgress,
    EpisodeScanReason,
    EpisodeScanRun,
    EpisodeScanRunId,
    EpisodeScanRunStatus,
    EpisodeScanSettings,
    EpisodeScanTrigger,
)
from media_manager.episode_scanner.service import (
    NO_DOWNLOAD_CLIENT_MESSAGE,
    NO_INDEXER_MESSAGE,
    UNREACHABLE_DOWNLOAD_CLIENT_MESSAGE,
    EpisodeScanRunner,
    EpisodeScanService,
    compute_next_scan_at,
    next_scheduler_tick,
    redact,
    torrent_matches_episode,
)
from media_manager.exceptions import ConflictError
from media_manager.indexer.schemas import IndexerQueryResult, IndexerQueryResultId
from media_manager.indexer.service import IndexerService
from media_manager.torrent.config import (
    QbittorrentConfig,
    SabnzbdConfig,
    TorrentConfig,
)
from media_manager.torrent.schemas import Quality, Torrent, TorrentStatus
from media_manager.tv.schemas import (
    Episode,
    EpisodeFileState,
    EpisodeId,
    EpisodeNumber,
    Season,
    SeasonNumber,
    Show,
    ShowId,
)
from media_manager.tv.service import TvService


def run(coroutine):  # noqa: ANN001, ANN201
    return asyncio.run(coroutine)


TODAY = datetime.now(UTC).date()


def make_result(
    title: str, *, score: int = 0, usenet: bool = False
) -> IndexerQueryResult:
    return IndexerQueryResult(
        title=title,
        download_url=f"magnet:?xt=urn:btih:{uuid4().hex}",
        seeders=10,
        flags=[],
        size=1_000_000,
        usenet=usenet,
        age=0,
        score=score,
        indexer="Prowlarr",
    )


def make_episode(number: int, air_date: date | None) -> Episode:
    return Episode(
        id=EpisodeId(uuid4()),
        number=EpisodeNumber(number),
        external_id=number,
        title=f"Episode {number}",
        air_date=air_date,
    )


def make_show(
    name: str = "Example Show",
    *,
    air_dates: list[date | None] | None = None,
    continuous_download: bool = True,
    ended: bool = False,
    season_monitored: bool = True,
) -> Show:
    dates = air_dates if air_dates is not None else [TODAY]
    return Show(
        id=ShowId(uuid4()),
        name=name,
        overview="",
        year=2026,
        external_id=1,
        metadata_provider="tmdb",
        continuous_download=continuous_download,
        ended=ended,
        seasons=[
            Season(
                number=SeasonNumber(1),
                name="Season 1",
                overview="",
                external_id=11,
                monitored=season_monitored,
                episodes=[
                    make_episode(number, air_date)
                    for number, air_date in enumerate(dates, start=1)
                ],
            )
        ],
    )


def make_torrent(title: str) -> Torrent:
    return Torrent(
        status=TorrentStatus.downloading,
        title=title,
        quality=Quality.fullhd,
        imported=False,
        hash=uuid4().hex,
    )


def make_run(
    *,
    status: EpisodeScanRunStatus = EpisodeScanRunStatus.running,
    started_at: datetime | None = None,
    trigger: EpisodeScanTrigger = EpisodeScanTrigger.scheduled,
) -> EpisodeScanRun:
    started = started_at or datetime.now(UTC)
    return EpisodeScanRun(
        id=EpisodeScanRunId(uuid4()),
        trigger=trigger,
        status=status,
        started_at=started,
        heartbeat_at=started,
    )


class FakeScanRepository:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.runs: list[EpisodeScanRun] = []
        self.items: list[EpisodeScanItem] = []
        self.progress_saves = 0
        self.interrupt_after_saves: int | None = None
        self.rollbacks = 0
        self.pruned_before: datetime | None = None

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def get_settings(self) -> EpisodeScanSettings:
        return EpisodeScanSettings(enabled=self.enabled, updated_at=datetime.now(UTC))

    async def set_enabled(self, enabled: bool) -> EpisodeScanSettings:
        self.enabled = enabled
        return await self.get_settings()

    async def recover_stale_runs(self, **_kwargs: object) -> int:
        return 0

    async def create_run(
        self,
        trigger: EpisodeScanTrigger,
        *,
        now: datetime | None = None,
    ) -> EpisodeScanRun | None:
        if any(run.status == EpisodeScanRunStatus.running for run in self.runs):
            return None
        new_run = make_run(trigger=trigger, started_at=now)
        self.runs.insert(0, new_run)
        return new_run

    async def get_run(self, run_id: EpisodeScanRunId) -> EpisodeScanRun:
        return next(run for run in self.runs if run.id == run_id)

    async def list_runs(self, *, limit: int = 10) -> list[EpisodeScanRun]:
        return sorted(self.runs, key=lambda run: run.started_at, reverse=True)[:limit]

    async def get_latest_run(self) -> EpisodeScanRun | None:
        runs = await self.list_runs(limit=1)
        return runs[0] if runs else None

    async def save_progress(
        self,
        run_id: EpisodeScanRunId,
        progress: EpisodeScanProgress,
        **_kwargs: object,
    ) -> bool:
        self.progress_saves += 1
        if self.interrupt_after_saves is not None and (
            self.progress_saves > self.interrupt_after_saves
        ):
            self._replace(run_id, status=EpisodeScanRunStatus.interrupted)
        if (await self.get_run(run_id)).status != EpisodeScanRunStatus.running:
            return False
        self._replace(run_id, **progress.model_dump())
        return True

    async def finish_run(
        self,
        run_id: EpisodeScanRunId,
        *,
        status: EpisodeScanRunStatus,
        progress: EpisodeScanProgress,
        message: str | None,
        **_kwargs: object,
    ) -> EpisodeScanRun:
        current = await self.get_run(run_id)
        if current.status != EpisodeScanRunStatus.running:
            return current
        return self._replace(
            run_id,
            status=status,
            message=message,
            finished_at=datetime.now(UTC),
            **progress.model_dump(),
        )

    async def add_item(self, item: EpisodeScanItem) -> EpisodeScanItem:
        self.items.append(item)
        return item

    async def list_items(
        self, run_id: EpisodeScanRunId, **_kwargs: object
    ) -> list[EpisodeScanItem]:
        return [item for item in self.items if item.run_id == run_id]

    async def list_recent_items(
        self,
        outcome: EpisodeScanOutcome,
        *,
        limit: int = 25,
    ) -> list[EpisodeScanItem]:
        return [item for item in reversed(self.items) if item.outcome == outcome][
            :limit
        ]

    async def delete_runs_started_before(self, cutoff: datetime) -> int:
        self.pruned_before = cutoff
        return 0

    def _replace(self, run_id: EpisodeScanRunId, **changes: Any) -> EpisodeScanRun:  # noqa: ANN401
        for index, existing in enumerate(self.runs):
            if existing.id == run_id:
                self.runs[index] = existing.model_copy(update=changes)
                return self.runs[index]
        raise AssertionError(run_id)

    def items_by_episode(self) -> dict[EpisodeId | None, EpisodeScanItem]:
        return {item.episode_id: item for item in self.items}


class FakeTvRepository:
    def __init__(self) -> None:
        self.file_states: dict[ShowId, dict[EpisodeId, EpisodeFileState]] = {}
        self.fail_for: set[ShowId] = set()

    async def get_episode_file_states(
        self, show_id: ShowId
    ) -> dict[EpisodeId, EpisodeFileState]:
        if show_id in self.fail_for:
            msg = "database hiccup"
            raise RuntimeError(msg)
        return dict(self.file_states.get(show_id, {}))


class FakeIndexerService:
    def __init__(self, *, enabled: bool = True) -> None:
        self.indexers = [object()] if enabled else []
        self.search_errors: list[str] = []

    def pop_search_errors(self) -> list[str]:
        errors, self.search_errors = self.search_errors, []
        return errors


class FakeTvService:
    def __init__(
        self,
        shows: list[Show],
        *,
        indexer_enabled: bool = True,
        torrent_client: bool = True,
        usenet_client: bool = False,
    ) -> None:
        self.shows = shows
        self.tv_repository = FakeTvRepository()
        self.indexer_service = FakeIndexerService(enabled=indexer_enabled)
        self.torrent_service = SimpleNamespace(
            download_manager=SimpleNamespace(
                has_torrent_client=torrent_client,
                has_usenet_client=usenet_client,
            )
        )
        self.releases: dict[EpisodeId, list[IndexerQueryResult]] = {}
        self.search_errors: dict[EpisodeId, list[str]] = {}
        self.download_errors: dict[EpisodeId, Exception] = {}
        self.searched: list[EpisodeId] = []
        self.downloaded: list[tuple[EpisodeId, IndexerQueryResultId]] = []

    async def get_all_shows(self) -> list[Show]:
        return list(self.shows)

    async def get_episode_releases(
        self,
        *,
        show: Show,  # noqa: ARG002
        episode_id: EpisodeId,
    ) -> list[IndexerQueryResult]:
        self.searched.append(episode_id)
        self.indexer_service.search_errors.extend(
            self.search_errors.get(episode_id, [])
        )
        return self.releases.get(episode_id, [])

    async def download_episode_release(
        self,
        *,
        show: Show,
        episode_id: EpisodeId,
        result_id: IndexerQueryResultId,
    ) -> Torrent:
        error = self.download_errors.get(episode_id)
        if error is not None:
            raise error
        self.downloaded.append((episode_id, result_id))
        self.tv_repository.file_states.setdefault(show.id, {})[episode_id] = (
            EpisodeFileState.DOWNLOADING
        )
        return make_torrent("release")


class FakeAutomationRepository:
    def __init__(self) -> None:
        self.targets: dict[ShowId, tuple[set[EpisodeId], bool]] = {}

    async def get_pending_show_targets(
        self, show_id: ShowId
    ) -> tuple[set[EpisodeId], bool]:
        return self.targets.get(show_id, (set(), False))


class FakeGateway:
    def __init__(
        self, names: list[str] | None = None, *, error: Exception | None = None
    ) -> None:
        self.names = names or []
        self.error = error

    def torrent_names(self) -> list[str]:
        if self.error is not None:
            raise self.error
        return self.names


def make_runner(
    tv_service: FakeTvService,
    *,
    repository: FakeScanRepository | None = None,
    automation_repository: FakeAutomationRepository | None = None,
    torrent_config: TorrentConfig | None = None,
    gateway: FakeGateway | None = None,
    **config_overrides: Any,  # noqa: ANN401
) -> tuple[EpisodeScanRunner, FakeScanRepository]:
    scan_repository = repository or FakeScanRepository()
    runner = EpisodeScanRunner(
        repository=cast(EpisodeScanRepository, scan_repository),
        tv_service=cast(TvService, tv_service),
        automation_repository=cast(
            AutomationRepository,
            automation_repository or FakeAutomationRepository(),
        ),
        config=EpisodeScannerConfig(**config_overrides),
        torrent_config=torrent_config,
        qbittorrent_gateway_factory=(
            (lambda: cast(QbittorrentGateway, gateway)) if gateway else None
        ),
    )
    return runner, scan_repository


def execute(
    runner: EpisodeScanRunner, repository: FakeScanRepository
) -> EpisodeScanRun:
    scan = run(repository.create_run(EpisodeScanTrigger.manual))
    assert scan is not None
    finished = run(runner.execute(scan.id))
    assert finished is not None
    return finished


def test_new_episode_is_sent_to_the_download_client() -> None:
    show = make_show()
    episode = show.seasons[0].episodes[0]
    tv_service = FakeTvService([show])
    best = make_result("Example.Show.S01E01.2160p", score=10)
    tv_service.releases[episode.id] = [best, make_result("Example.Show.S01E01.720p")]
    runner, repository = make_runner(tv_service)

    finished = execute(runner, repository)

    assert tv_service.downloaded == [(episode.id, best.id)]
    assert finished.status == EpisodeScanRunStatus.succeeded
    assert finished.shows_total == finished.shows_checked == 1
    assert (finished.episodes_found, finished.episodes_sent, finished.errors) == (
        1,
        1,
        0,
    )
    item = repository.items_by_episode()[episode.id]
    assert item.outcome == EpisodeScanOutcome.sent
    assert item.release_title == best.title
    assert (item.show_name, item.season_number, item.episode_number) == (
        "Example Show",
        1,
        1,
    )
    assert repository.pruned_before is not None


def test_episodes_already_in_library_downloading_queued_or_in_client_are_skipped() -> (
    None
):
    show = make_show(air_dates=[TODAY] * 5)
    episodes = show.seasons[0].episodes
    tv_service = FakeTvService([show])
    tv_service.tv_repository.file_states[show.id] = {
        episodes[0].id: EpisodeFileState.IN_LIBRARY,
        episodes[1].id: EpisodeFileState.DOWNLOADING,
    }
    automation = FakeAutomationRepository()
    automation.targets[show.id] = ({episodes[2].id}, False)
    gateway = FakeGateway(
        ["Example.Show.S01E04.1080p.WEB-DL", "Other.Show.S01E05.1080p"]
    )
    fresh = make_result("Example.Show.S01E05.1080p")
    tv_service.releases[episodes[4].id] = [fresh]
    runner, repository = make_runner(
        tv_service,
        automation_repository=automation,
        torrent_config=TorrentConfig(qbittorrent=QbittorrentConfig(enabled=True)),
        gateway=gateway,
    )

    finished = execute(runner, repository)

    items = repository.items_by_episode()
    assert [items[episode.id].reason for episode in episodes[:4]] == [
        EpisodeScanReason.in_library,
        EpisodeScanReason.downloading,
        EpisodeScanReason.queued,
        EpisodeScanReason.in_download_client,
    ]
    assert items[episodes[4].id].outcome == EpisodeScanOutcome.sent
    # Only the one genuinely new episode reached the indexers.
    assert tv_service.searched == [episodes[4].id]
    assert (
        finished.episodes_found,
        finished.episodes_skipped,
        finished.episodes_sent,
    ) == (5, 4, 1)


def test_running_show_job_owns_the_whole_show() -> None:
    show = make_show()
    tv_service = FakeTvService([show])
    automation = FakeAutomationRepository()
    automation.targets[show.id] = (set(), True)
    runner, repository = make_runner(tv_service, automation_repository=automation)

    execute(runner, repository)

    assert tv_service.searched == []
    assert repository.items[0].reason == EpisodeScanReason.queued


def test_only_recently_aired_regular_episodes_are_new() -> None:
    show = make_show(
        air_dates=[
            TODAY - timedelta(days=30),  # older than the look-back window
            TODAY - timedelta(days=14),  # first day of the window
            TODAY + timedelta(days=1),  # not aired yet
            None,  # unknown air date
        ]
    )
    show.seasons.append(
        Season(
            number=SeasonNumber(0),
            name="Specials",
            overview="",
            external_id=10,
            episodes=[make_episode(1, TODAY)],
        )
    )
    tv_service = FakeTvService([show])
    runner, repository = make_runner(tv_service, lookback_days=14)

    finished = execute(runner, repository)

    assert tv_service.searched == [show.seasons[0].episodes[1].id]
    assert finished.episodes_found == 1
    assert finished.episodes_not_found == 1
    assert repository.items[0].outcome == EpisodeScanOutcome.not_found


def test_unmonitored_show_is_checked_but_never_downloaded() -> None:
    show = make_show(continuous_download=False, season_monitored=False)
    tv_service = FakeTvService([show])
    tv_service.releases[show.seasons[0].episodes[0].id] = [
        make_result("Example.Show.S01E01")
    ]
    runner, repository = make_runner(tv_service)

    finished = execute(runner, repository)

    assert tv_service.searched == []
    assert repository.items[0].reason == EpisodeScanReason.not_monitored
    assert finished.shows_checked == 1
    assert finished.status == EpisodeScanRunStatus.succeeded


def test_unmonitored_season_of_monitored_show_is_skipped() -> None:
    show = make_show(season_monitored=False)
    tv_service = FakeTvService([show])
    runner, repository = make_runner(tv_service)

    execute(runner, repository)

    assert tv_service.searched == []
    assert repository.items[0].reason == EpisodeScanReason.season_not_monitored


def test_finale_of_a_show_that_just_ended_is_still_downloaded() -> None:
    # Metadata refreshes turn continuous download off once a show has ended.
    show = make_show(continuous_download=False, ended=True, season_monitored=True)
    finale = show.seasons[0].episodes[0]
    tv_service = FakeTvService([show])
    tv_service.releases[finale.id] = [make_result("Example.Show.S01E01.1080p")]
    runner, repository = make_runner(tv_service)

    execute(runner, repository)

    assert [episode_id for episode_id, _ in tv_service.downloaded] == [finale.id]


def test_a_failing_show_does_not_stop_the_other_shows() -> None:
    broken = make_show("Alpha")
    healthy = make_show("Beta")
    tv_service = FakeTvService([healthy, broken])
    tv_service.tv_repository.fail_for.add(broken.id)
    healthy_episode = healthy.seasons[0].episodes[0]
    tv_service.releases[healthy_episode.id] = [make_result("Beta.S01E01.1080p")]
    runner, repository = make_runner(tv_service)

    finished = execute(runner, repository)

    assert finished.status == EpisodeScanRunStatus.completed_with_errors
    assert (finished.shows_checked, finished.shows_failed, finished.errors) == (1, 1, 1)
    show_error = next(item for item in repository.items if item.show_id == broken.id)
    assert show_error.outcome == EpisodeScanOutcome.error
    assert show_error.reason == EpisodeScanReason.unexpected
    assert show_error.episode_id is None
    assert "database hiccup" in (show_error.message or "")
    assert [episode_id for episode_id, _ in tv_service.downloaded] == [
        healthy_episode.id
    ]
    assert repository.rollbacks >= 1


def test_indexer_failure_is_a_clear_redacted_search_error() -> None:
    show = make_show()
    episode = show.seasons[0].episodes[0]
    tv_service = FakeTvService([show])
    tv_service.search_errors[episode.id] = [
        "Jackett: HTTPError: 500 for url: "
        "http://jackett:9117/api/v2.0/indexers/all/results/torznab/api?apikey=SECRET123&t=tvsearch"
    ]
    runner, repository = make_runner(tv_service)

    finished = execute(runner, repository)

    item = repository.items[0]
    assert item.outcome == EpisodeScanOutcome.error
    assert item.reason == EpisodeScanReason.search
    assert "Jackett" in (item.message or "")
    assert "SECRET123" not in (item.message or "")
    assert finished.status == EpisodeScanRunStatus.completed_with_errors


def test_download_failure_is_reported_and_the_next_episode_is_still_sent() -> None:
    show = make_show(air_dates=[TODAY, TODAY])
    first, second = show.seasons[0].episodes
    tv_service = FakeTvService([show])
    tv_service.releases[first.id] = [make_result("Example.Show.S01E01.1080p")]
    tv_service.releases[second.id] = [make_result("Example.Show.S01E02.1080p")]
    tv_service.download_errors[first.id] = RuntimeError(
        "qBittorrent refused the torrent"
    )
    runner, repository = make_runner(tv_service)

    finished = execute(runner, repository)

    items = repository.items_by_episode()
    assert items[first.id].outcome == EpisodeScanOutcome.error
    assert items[first.id].reason == EpisodeScanReason.download
    assert "qBittorrent refused the torrent" in (items[first.id].message or "")
    assert items[second.id].outcome == EpisodeScanOutcome.sent
    assert (finished.episodes_sent, finished.errors) == (1, 1)


def test_episode_claimed_by_another_download_meanwhile_is_a_skip() -> None:
    show = make_show()
    episode = show.seasons[0].episodes[0]
    tv_service = FakeTvService([show])
    tv_service.releases[episode.id] = [make_result("Example.Show.S01E01.1080p")]

    class ClaimedMeanwhileError(ConflictError):
        def __init__(self) -> None:
            super().__init__("Episode S01E01 is already managed.")
            tv_service.tv_repository.file_states[show.id] = {
                episode.id: EpisodeFileState.DOWNLOADING
            }

    async def download_episode_release(
        *,
        show: Show,  # noqa: ARG001
        episode_id: EpisodeId,  # noqa: ARG001
        result_id: IndexerQueryResultId,  # noqa: ARG001
    ) -> Torrent:
        raise ClaimedMeanwhileError

    setattr(tv_service, "download_episode_release", download_episode_release)  # noqa: B010
    runner, repository = make_runner(tv_service)

    finished = execute(runner, repository)

    assert repository.items[0].outcome == EpisodeScanOutcome.skipped
    assert repository.items[0].reason == EpisodeScanReason.downloading
    assert finished.status == EpisodeScanRunStatus.succeeded


@pytest.mark.parametrize(
    ("indexer_enabled", "torrent_client", "torrent_config", "expected"),
    [
        (False, True, None, NO_INDEXER_MESSAGE),
        (True, False, TorrentConfig(), NO_DOWNLOAD_CLIENT_MESSAGE),
        (
            True,
            False,
            TorrentConfig(qbittorrent=QbittorrentConfig(enabled=True)),
            UNREACHABLE_DOWNLOAD_CLIENT_MESSAGE,
        ),
    ],
)
def test_missing_configuration_is_reported_without_searching(
    indexer_enabled: bool,
    torrent_client: bool,
    torrent_config: TorrentConfig | None,
    expected: str,
) -> None:
    show = make_show()
    tv_service = FakeTvService(
        [show],
        indexer_enabled=indexer_enabled,
        torrent_client=torrent_client,
    )
    runner, repository = make_runner(tv_service, torrent_config=torrent_config)

    finished = execute(runner, repository)

    assert tv_service.searched == []
    assert repository.items[0].reason == EpisodeScanReason.configuration
    assert repository.items[0].message == expected
    assert expected in (finished.message or "")
    assert finished.status == EpisodeScanRunStatus.completed_with_errors


def test_release_the_client_cannot_accept_is_passed_over() -> None:
    show = make_show()
    episode = show.seasons[0].episodes[0]
    tv_service = FakeTvService([show], torrent_client=True, usenet_client=False)
    usenet = make_result("Example.Show.S01E01.2160p", score=100, usenet=True)
    torrent = make_result("Example.Show.S01E01.1080p", score=1)
    tv_service.releases[episode.id] = [usenet, torrent]
    runner, repository = make_runner(
        tv_service,
        torrent_config=TorrentConfig(sabnzbd=SabnzbdConfig(enabled=False)),
    )

    execute(runner, repository)

    assert tv_service.downloaded == [(episode.id, torrent.id)]


def test_unreadable_client_list_is_a_note_not_a_failure() -> None:
    show = make_show()
    episode = show.seasons[0].episodes[0]
    tv_service = FakeTvService([show])
    tv_service.releases[episode.id] = [make_result("Example.Show.S01E01.1080p")]
    runner, repository = make_runner(
        tv_service,
        torrent_config=TorrentConfig(qbittorrent=QbittorrentConfig(enabled=True)),
        gateway=FakeGateway(error=ConnectionError("refused")),
    )

    finished = execute(runner, repository)

    assert finished.status == EpisodeScanRunStatus.succeeded
    assert "qBittorrent" in (finished.message or "")
    assert repository.items[0].outcome == EpisodeScanOutcome.sent


def test_execute_does_nothing_for_a_run_that_is_no_longer_running() -> None:
    tv_service = FakeTvService([make_show()])
    runner, repository = make_runner(tv_service)
    interrupted = make_run(status=EpisodeScanRunStatus.interrupted)
    repository.runs.append(interrupted)

    result = run(runner.execute(interrupted.id))

    assert result == interrupted
    assert tv_service.searched == []
    assert repository.items == []


def test_scan_stops_when_its_run_was_marked_interrupted_meanwhile() -> None:
    shows = [make_show(name) for name in ("Alpha", "Beta", "Gamma")]
    tv_service = FakeTvService(shows)
    for show in shows:
        episode = show.seasons[0].episodes[0]
        tv_service.releases[episode.id] = [make_result(f"{show.name}.S01E01.1080p")]
    repository = FakeScanRepository()
    # Start, total, first show... then another worker declares the run dead.
    repository.interrupt_after_saves = 3
    runner, _ = make_runner(tv_service, repository=repository)

    finished = execute(runner, repository)

    assert finished.status == EpisodeScanRunStatus.interrupted
    assert len(tv_service.downloaded) < len(shows)


def test_keep_alive_notices_a_lost_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[EpisodeScanRunId] = []

    async def lease_keeper(run_id: EpisodeScanRunId) -> bool:
        calls.append(run_id)
        return len(calls) < 2

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    runner, _ = make_runner(FakeTvService([]))
    runner.lease_keeper = lease_keeper
    run_id = EpisodeScanRunId(uuid4())

    run(runner._keep_alive(run_id))

    assert calls == [run_id, run_id]
    assert runner._lease_lost is True


def test_scheduled_scan_starts_only_when_enabled_and_due() -> None:
    repository = FakeScanRepository(enabled=True)
    service = EpisodeScanService(
        cast(EpisodeScanRepository, repository),
        EpisodeScannerConfig(interval_minutes=60),
    )
    now = datetime(2026, 9, 25, 13, 0, 0, 400_000, tzinfo=UTC)

    first = run(service.start_scheduled_scan_if_due(now=now))
    assert first is not None
    assert first.trigger == EpisodeScanTrigger.scheduled
    # Nothing new starts while a scan is running.
    assert (
        run(service.start_scheduled_scan_if_due(now=now + timedelta(hours=2))) is None
    )

    repository._replace(first.id, status=EpisodeScanRunStatus.succeeded)
    assert (
        run(service.start_scheduled_scan_if_due(now=now + timedelta(minutes=30)))
        is None
    )
    # The next tick fires a fraction of a second "early" relative to the start.
    second = run(
        service.start_scheduled_scan_if_due(
            now=now + timedelta(minutes=59, seconds=59, milliseconds=900)
        )
    )
    assert second is not None

    repository._replace(second.id, status=EpisodeScanRunStatus.succeeded)
    repository.enabled = False
    assert (
        run(service.start_scheduled_scan_if_due(now=now + timedelta(hours=5))) is None
    )


def test_manual_scan_is_refused_while_another_scan_runs() -> None:
    repository = FakeScanRepository(enabled=False)
    service = EpisodeScanService(cast(EpisodeScanRepository, repository))

    manual = run(service.start_manual_scan())

    assert manual.trigger == EpisodeScanTrigger.manual
    with pytest.raises(ConflictError):
        run(service.start_manual_scan())


def test_status_reports_latest_results_and_the_next_scan() -> None:
    repository = FakeScanRepository(enabled=True)
    finished = make_run(
        status=EpisodeScanRunStatus.succeeded,
        started_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    repository.runs.append(finished)
    sent = EpisodeScanItem(
        run_id=finished.id,
        show_name="Example Show",
        season_number=1,
        episode_number=1,
        outcome=EpisodeScanOutcome.sent,
        release_title="Example.Show.S01E01.1080p",
    )
    repository.items.append(sent)
    service = EpisodeScanService(cast(EpisodeScanRepository, repository))

    status = run(service.get_status())

    assert status.enabled is True
    assert status.running is False
    assert status.latest_run == finished
    assert status.latest_items == [sent]
    assert status.recent_sent == [sent]
    assert status.next_scan_at is not None
    assert status.next_scan_at >= finished.started_at + timedelta(minutes=59)

    repository.enabled = False
    assert run(service.get_status()).next_scan_at is None


def test_next_scan_is_rounded_to_the_scheduler_tick() -> None:
    now = datetime(2026, 9, 25, 12, 10, tzinfo=UTC)
    interval = timedelta(hours=1)
    assert compute_next_scan_at(
        enabled=True,
        interval=interval,
        last_started_at=datetime(2026, 9, 25, 12, 0, 0, 700_000, tzinfo=UTC),
        now=now,
    ) == datetime(2026, 9, 25, 13, 0, tzinfo=UTC)
    # A manual scan at 12:32 moves the next scheduled scan to the 13:35 tick.
    assert compute_next_scan_at(
        enabled=True,
        interval=interval,
        last_started_at=datetime(2026, 9, 25, 12, 32, 10, tzinfo=UTC),
        now=datetime(2026, 9, 25, 12, 33, tzinfo=UTC),
    ) == datetime(2026, 9, 25, 13, 35, tzinfo=UTC)
    # Never scanned before: the next tick.
    assert compute_next_scan_at(
        enabled=True,
        interval=interval,
        last_started_at=None,
        now=datetime(2026, 9, 25, 12, 7, 30, tzinfo=UTC),
    ) == datetime(2026, 9, 25, 12, 10, tzinfo=UTC)
    assert (
        compute_next_scan_at(
            enabled=False,
            interval=interval,
            last_started_at=None,
            now=now,
        )
        is None
    )
    assert next_scheduler_tick(now) == now


@pytest.mark.parametrize(
    ("torrent_name", "season", "episode", "expected"),
    [
        ("Example.Show.S01E02.1080p.WEB-DL", 1, 2, True),
        ("Example Show S01E01E02 720p", 1, 2, True),
        ("Example.Show.S01E01-E03.2160p", 1, 2, True),
        ("Example.Show.2026.S01E02.1080p", 1, 2, True),
        ("Example.Show.US.S01E02.1080p", 1, 2, True),
        ("Example.Show.1x02.HDTV", 1, 2, True),
        ("Example.Show.S01.COMPLETE.1080p", 1, 2, False),
        ("Example.Show.S01E12.1080p", 1, 2, False),
        ("Example.Show.S02E02.1080p", 1, 2, False),
        ("Another.Show.S01E02.1080p", 1, 2, False),
        ("Example.Show.Behind.The.Scenes.S01E02", 1, 2, False),
        ("Example.Show.S01E02.1920x1080", 1, 2, True),
        ("Something.Else.1920x1080", 19, 20, False),
    ],
)
def test_download_client_torrent_matching(
    torrent_name: str,
    season: int,
    episode: int,
    expected: bool,
) -> None:
    assert (
        torrent_matches_episode(
            torrent_name,
            show_name="Example Show",
            season_number=season,
            episode_number=episode,
        )
        is expected
    )


def test_redact_removes_urls_queries_and_keys() -> None:
    message = redact(
        "HTTPError for url: https://user:pw@tracker.example/download.php?id=1&passkey=abc "
        "and apikey=SECRET token=xyz"
    )

    assert "abc" not in message
    assert "pw@" not in message
    assert "SECRET" not in message
    assert "xyz" not in message
    assert "https://tracker.example/download.php" in message


def test_indexer_service_collects_tolerated_upstream_failures() -> None:
    class PartlyFailingIndexer:
        max_results = 10

        def __init__(self) -> None:
            self.failures = ["Tracker A: HTTPError (HTTP 429)"]

        def search_episode(self, **_kwargs: object) -> list[IndexerQueryResult]:
            return [make_result("Example.Show.S01E01.1080p")]

        def pop_tolerated_failures(self) -> list[str]:
            failures, self.failures = self.failures, []
            return failures

    service = object.__new__(IndexerService)
    service.indexers = cast(Any, [PartlyFailingIndexer()])
    service.search_errors = []
    service.repository = cast(Any, SimpleNamespace(save_results=AsyncMock()))

    results = run(
        service.search_episode(show=make_show(), season_number=1, episode_number=1)
    )

    assert len(results) == 1
    assert service.pop_search_errors() == [
        "PartlyFailingIndexer: Tracker A: HTTPError (HTTP 429)"
    ]


def test_indexer_service_records_failures_for_the_scanner() -> None:
    class BrokenIndexer:
        max_results = 10

        def search_episode(self, **_kwargs: object) -> list[IndexerQueryResult]:
            msg = "connection refused"
            raise ConnectionError(msg)

    class WorkingIndexer:
        max_results = 10

        def search_episode(self, **_kwargs: object) -> list[IndexerQueryResult]:
            return [make_result("Example.Show.S01E01.1080p")]

    service = object.__new__(IndexerService)
    service.indexers = cast(Any, [BrokenIndexer(), WorkingIndexer()])
    service.search_errors = []
    service.repository = cast(Any, SimpleNamespace(save_results=AsyncMock()))

    results = run(
        service.search_episode(show=make_show(), season_number=1, episode_number=1)
    )

    assert len(results) == 1
    assert service.pop_search_errors() == [
        "BrokenIndexer: ConnectionError: connection refused"
    ]
    assert service.pop_search_errors() == []
