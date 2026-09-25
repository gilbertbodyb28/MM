# ruff: noqa: S101

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

from media_manager.automation.config import AutomationConfig
from media_manager.automation.schemas import (
    AutomationJob,
    AutomationJobId,
    AutomationJobKind,
    AutomationJobStatus,
)
from media_manager.automation.service import AutomationService
from media_manager.indexer.schemas import IndexerQueryResult, IndexerQueryResultId
from media_manager.movies.schemas import Movie, MovieId
from media_manager.torrent.config import QbittorrentConfig, TorrentConfig
from media_manager.torrent.schemas import Quality, Torrent, TorrentStatus
from media_manager.tv.schemas import (
    Episode,
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


def make_result(
    title: str,
    *,
    seeders: int = 10,
    score: int = 0,
    usenet: bool = False,
) -> IndexerQueryResult:
    return IndexerQueryResult(
        title=title,
        download_url=f"magnet:?xt=urn:btih:{uuid4().hex}",
        seeders=seeders,
        flags=[],
        size=1_000_000,
        usenet=usenet,
        age=0,
        score=score,
        indexer="test",
    )


def make_movie() -> Movie:
    return Movie(
        id=MovieId(uuid4()),
        name="Example Movie",
        overview="",
        year=2026,
        external_id=1,
        metadata_provider="tmdb",
    )


def make_show() -> Show:
    today = datetime.now(UTC).date()
    return Show(
        id=ShowId(uuid4()),
        name="Example Show",
        overview="",
        year=2026,
        external_id=2,
        metadata_provider="tmdb",
        continuous_download=True,
        seasons=[
            Season(
                number=SeasonNumber(1),
                name="Season 1",
                overview="",
                external_id=11,
                episodes=[
                    Episode(
                        id=EpisodeId(uuid4()),
                        number=EpisodeNumber(1),
                        external_id=111,
                        title="One",
                        air_date=today,
                    ),
                    Episode(
                        id=EpisodeId(uuid4()),
                        number=EpisodeNumber(2),
                        external_id=112,
                        title="Two",
                        air_date=today,
                    ),
                ],
            ),
            Season(
                number=SeasonNumber(2),
                name="Season 2",
                overview="",
                external_id=12,
                episodes=[
                    Episode(
                        id=EpisodeId(uuid4()),
                        number=EpisodeNumber(1),
                        external_id=121,
                        title="One",
                        air_date=today,
                    )
                ],
            ),
        ],
    )


def make_job(
    *,
    kind: AutomationJobKind,
    movie_id: MovieId | None = None,
    show_id: ShowId | None = None,
    episode_id: EpisodeId | None = None,
    attempts: int = 1,
) -> AutomationJob:
    now = datetime.now(UTC)
    return AutomationJob(
        id=AutomationJobId(uuid4()),
        job_key=f"{kind.value}:{episode_id or movie_id or show_id}",
        kind=kind,
        status=AutomationJobStatus.searching,
        movie_id=movie_id,
        show_id=show_id,
        episode_id=episode_id,
        attempts=attempts,
        next_attempt_at=now,
        created_at=now,
        updated_at=now,
        started_at=now,
        locked_at=now,
    )


def make_torrent(title: str) -> Torrent:
    return Torrent(
        status=TorrentStatus.downloading,
        title=title,
        quality=Quality.uhd,
        imported=False,
        hash=uuid4().hex,
    )


class FakeAutomationRepository:
    def __init__(self, job: AutomationJob) -> None:
        self.job = job
        self.downloading_results: list[IndexerQueryResult] = []
        self.retry_arguments: dict[str, object] = {}

    async def get_job(self, _job_id: AutomationJobId) -> AutomationJob:
        return self.job

    async def mark_downloading(
        self,
        _job_id: AutomationJobId,
        *,
        result: IndexerQueryResult,
        torrent: Torrent | None = None,  # noqa: ARG002
        message: str | None = None,  # noqa: ARG002
    ) -> AutomationJob:
        self.downloading_results.append(result)
        self.job = self.job.model_copy(
            update={"status": AutomationJobStatus.downloading}
        )
        return self.job

    async def mark_succeeded(
        self,
        _job_id: AutomationJobId,
        *,
        message: str,  # noqa: ARG002
    ) -> AutomationJob:
        self.job = self.job.model_copy(update={"status": AutomationJobStatus.succeeded})
        return self.job

    async def mark_skipped(
        self,
        _job_id: AutomationJobId,
        *,
        message: str,  # noqa: ARG002
    ) -> AutomationJob:
        self.job = self.job.model_copy(update={"status": AutomationJobStatus.skipped})
        return self.job

    async def mark_retry_or_failed(
        self, _job_id: AutomationJobId, **kwargs: object
    ) -> AutomationJob:
        self.retry_arguments = kwargs
        max_attempts = kwargs["max_attempts"]
        assert isinstance(max_attempts, int)
        status = (
            AutomationJobStatus.failed
            if self.job.attempts >= max_attempts
            else AutomationJobStatus.retry_wait
        )
        self.job = self.job.model_copy(update={"status": status})
        return self.job


class FakeMovieRepository:
    def __init__(self) -> None:
        self.managed = False

    async def has_movie_file(self, _movie_id: MovieId) -> bool:
        return self.managed


class FakeMovieService:
    def __init__(self, movie: Movie, releases: list[IndexerQueryResult]) -> None:
        self.movie = movie
        self.releases = releases
        self.movie_repository = FakeMovieRepository()
        self.downloaded_result_ids = []

    async def get_movie_by_id(self, _movie_id: MovieId) -> Movie:
        return self.movie

    async def get_all_available_torrents_for_movie(
        self, _movie: Movie
    ) -> list[IndexerQueryResult]:
        return self.releases

    async def download_torrent(
        self,
        *,
        public_indexer_result_id: IndexerQueryResultId,
        movie: Movie,  # noqa: ARG002
    ) -> Torrent:
        self.downloaded_result_ids.append(public_indexer_result_id)
        self.movie_repository.managed = True
        selected = next(
            release
            for release in self.releases
            if release.id == public_indexer_result_id
        )
        return make_torrent(selected.title)


class FakeTvRepository:
    def __init__(self) -> None:
        self.managed: set[EpisodeId] = set()

    async def get_managed_episode_ids(self, _show_id: ShowId) -> set[EpisodeId]:
        return set(self.managed)


class FakeTvService:
    def __init__(
        self,
        show: Show,
        season_releases: dict[int, list[IndexerQueryResult]],
        episode_releases: list[IndexerQueryResult] | None = None,
    ) -> None:
        self.show = show
        self.season_releases = season_releases
        self.episode_releases = episode_releases or []
        self.tv_repository = FakeTvRepository()
        self.download_calls: list[set[EpisodeId]] = []
        self.indexer_service = SimpleNamespace(
            search_episode=AsyncMock(return_value=self.episode_releases)
        )

    async def get_show_by_id(self, _show_id: ShowId) -> Show:
        return self.show

    async def get_all_available_torrents_for_a_season(
        self,
        *,
        season_number: int,
        show_id: ShowId,  # noqa: ARG002
    ) -> list[IndexerQueryResult]:
        return self.season_releases.get(season_number, [])

    async def download_torrent(
        self,
        *,
        public_indexer_result_id: IndexerQueryResultId,
        show_id: ShowId,  # noqa: ARG002
        episode_ids: set[EpisodeId],
    ) -> Torrent:
        self.download_calls.append(set(episode_ids))
        self.tv_repository.managed.update(episode_ids)
        releases = [
            release for values in self.season_releases.values() for release in values
        ] + self.episode_releases
        selected = next(
            release for release in releases if release.id == public_indexer_result_id
        )
        return make_torrent(selected.title)

    async def get_episode_releases(
        self,
        *,
        show: Show,  # noqa: ARG002
        episode_id: EpisodeId,  # noqa: ARG002
    ) -> list[IndexerQueryResult]:
        return self.episode_releases

    async def download_episode_release(
        self,
        *,
        show: Show,  # noqa: ARG002
        episode_id: EpisodeId,
        result_id: IndexerQueryResultId,
    ) -> Torrent:
        self.download_calls.append({episode_id})
        self.tv_repository.managed.add(episode_id)
        selected = next(
            release for release in self.episode_releases if release.id == result_id
        )
        return make_torrent(selected.title)


def make_service(
    repository: FakeAutomationRepository,
    movie_service: Any,  # noqa: ANN401
    tv_service: Any,  # noqa: ANN401
    torrent_config: TorrentConfig | None = None,
    **config_overrides: Any,  # noqa: ANN401
) -> AutomationService:
    config = AutomationConfig(
        enabled=True,
        base_backoff_seconds=10,
        max_backoff_seconds=100,
        exhausted_retry_seconds=1000,
        **config_overrides,
    )
    return AutomationService(
        repository=repository,
        movie_service=movie_service,
        tv_service=tv_service,
        config=config,
        torrent_config=torrent_config,
    )


def test_movie_job_selects_highest_priority_quality() -> None:
    movie = make_movie()
    full_hd = make_result("Example.Movie.2026.1080p", seeders=100, score=1000)
    ultra_hd = make_result("Example.Movie.2026.2160p", seeders=1, score=1)
    job = make_job(kind=AutomationJobKind.movie, movie_id=movie.id)
    repository = FakeAutomationRepository(job)
    movie_service = FakeMovieService(movie, [full_hd, ultra_hd])
    service = make_service(
        repository,
        movie_service,
        SimpleNamespace(),
    )

    status = run(service.process_job(job))

    assert status == AutomationJobStatus.succeeded
    assert movie_service.downloaded_result_ids == [ultra_hd.id]
    assert repository.downloading_results == [ultra_hd]


def test_process_due_jobs_claims_only_when_the_worker_is_ready() -> None:
    movie = make_movie()
    jobs = [make_job(kind=AutomationJobKind.movie, movie_id=movie.id) for _ in range(3)]
    events: list[tuple[str, AutomationJobId]] = []

    class ClaimingRepository:
        def __init__(self) -> None:
            self.remaining = list(jobs)
            self.claim_limits: list[int] = []

        async def claim_due_jobs(
            self,
            *,
            limit: int,
            lease_timeout_seconds: int,  # noqa: ARG002
            kinds: frozenset[AutomationJobKind] | None = None,  # noqa: ARG002
        ) -> list[AutomationJob]:
            self.claim_limits.append(limit)
            if not self.remaining:
                return []
            job = self.remaining.pop(0)
            events.append(("claim", job.id))
            return [job]

    repository = ClaimingRepository()
    service = make_service(
        repository,  # type: ignore[arg-type]
        SimpleNamespace(),
        SimpleNamespace(),
        process_batch_size=2,
    )

    async def process_job(job: AutomationJob) -> AutomationJobStatus:
        events.append(("process", job.id))
        return AutomationJobStatus.succeeded

    service.process_job = process_job  # type: ignore[method-assign]

    result = run(service.process_due_jobs())

    assert repository.claim_limits == [1, 1]
    assert events == [
        ("claim", jobs[0].id),
        ("process", jobs[0].id),
        ("claim", jobs[1].id),
        ("process", jobs[1].id),
    ]
    assert result.claimed == 2
    assert result.succeeded == 2
    assert result.job_ids == [jobs[0].id, jobs[1].id]


def test_movie_job_skips_incompatible_usenet_release() -> None:
    movie = make_movie()
    usenet = make_result("Example.Movie.2026.2160p", score=1000, usenet=True)
    torrent = make_result("Example.Movie.2026.1080p", score=100)
    job = make_job(kind=AutomationJobKind.movie, movie_id=movie.id)
    repository = FakeAutomationRepository(job)
    movie_service = FakeMovieService(movie, [usenet, torrent])
    service = make_service(
        repository,
        movie_service,
        SimpleNamespace(),
        torrent_config=TorrentConfig(
            qbittorrent=QbittorrentConfig(enabled=True),
        ),
    )

    status = run(service.process_job(job))

    assert status == AutomationJobStatus.succeeded
    assert movie_service.downloaded_result_ids == [torrent.id]
    assert repository.downloading_results == [torrent]


def test_show_job_uses_one_multi_season_pack_for_all_missing_episodes() -> None:
    show = make_show()
    pack = make_result("Example.Show.S01-S02.2160p")
    job = make_job(kind=AutomationJobKind.show, show_id=show.id)
    repository = FakeAutomationRepository(job)
    tv_service = FakeTvService(show, {1: [pack], 2: [pack]})
    service = make_service(repository, SimpleNamespace(), tv_service)

    status = run(service.process_job(job))

    expected = {episode.id for season in show.seasons for episode in season.episodes}
    assert status == AutomationJobStatus.succeeded
    assert tv_service.download_calls == [expected]
    assert repository.downloading_results == [pack]


def test_show_job_skips_when_every_episode_is_already_managed() -> None:
    show = make_show()
    job = make_job(kind=AutomationJobKind.show, show_id=show.id)
    repository = FakeAutomationRepository(job)
    tv_service = FakeTvService(show, {})
    tv_service.tv_repository.managed = {
        episode.id for season in show.seasons for episode in season.episodes
    }
    service = make_service(repository, SimpleNamespace(), tv_service)

    status = run(service.process_job(job))

    assert status == AutomationJobStatus.skipped
    assert tv_service.download_calls == []


def test_show_job_does_not_download_unaired_episodes() -> None:
    show = make_show()
    aired_episode = show.seasons[0].episodes[0]
    future_episode = show.seasons[0].episodes[1]
    today = datetime.now(UTC).date()
    aired_episode.air_date = today - timedelta(days=1)
    future_episode.air_date = today + timedelta(days=1)
    show.seasons[1].episodes[0].air_date = today + timedelta(days=7)
    release = make_result("Example.Show.S01.2160p")
    job = make_job(kind=AutomationJobKind.show, show_id=show.id)
    repository = FakeAutomationRepository(job)
    tv_service = FakeTvService(show, {1: [release]})
    service = make_service(repository, SimpleNamespace(), tv_service)

    status = run(service.process_job(job))

    assert status == AutomationJobStatus.succeeded
    assert tv_service.download_calls == [{aired_episode.id}]
    assert future_episode.id not in tv_service.tv_repository.managed


def test_show_job_does_not_download_episode_with_unknown_air_date() -> None:
    show = make_show()
    known_episode = show.seasons[0].episodes[0]
    unknown_episode = show.seasons[0].episodes[1]
    unknown_episode.air_date = None
    show.seasons[1].episodes[0].air_date = datetime.now(UTC).date() + timedelta(days=7)
    release = make_result("Example.Show.S01.2160p")
    job = make_job(kind=AutomationJobKind.show, show_id=show.id)
    repository = FakeAutomationRepository(job)
    tv_service = FakeTvService(show, {1: [release]})
    service = make_service(repository, SimpleNamespace(), tv_service)

    status = run(service.process_job(job))

    assert status == AutomationJobStatus.succeeded
    assert tv_service.download_calls == [{known_episode.id}]
    assert unknown_episode.id not in tv_service.tv_repository.managed


def test_show_job_only_downloads_monitored_seasons() -> None:
    show = make_show()
    show.seasons[1].monitored = False
    season_one_release = make_result("Example.Show.S01.2160p")
    job = make_job(kind=AutomationJobKind.show, show_id=show.id)
    repository = FakeAutomationRepository(job)
    tv_service = FakeTvService(show, {1: [season_one_release]})
    service = make_service(repository, SimpleNamespace(), tv_service)

    status = run(service.process_job(job))

    expected = {episode.id for episode in show.seasons[0].episodes}
    unmonitored = {episode.id for episode in show.seasons[1].episodes}
    assert status == AutomationJobStatus.succeeded
    assert tv_service.download_calls == [expected]
    assert unmonitored.isdisjoint(tv_service.tv_repository.managed)


def test_show_job_skips_if_show_was_unmonitored_after_enqueue() -> None:
    show = make_show()
    show.continuous_download = False
    job = make_job(kind=AutomationJobKind.show, show_id=show.id)
    repository = FakeAutomationRepository(job)
    tv_service = FakeTvService(show, {})
    service = make_service(repository, SimpleNamespace(), tv_service)

    status = run(service.process_job(job))

    assert status == AutomationJobStatus.skipped
    assert tv_service.indexer_service.search_episode.await_count == 0
    assert tv_service.download_calls == []


def test_episode_job_selects_best_exact_release_and_targets_only_that_episode() -> None:
    show = make_show()
    episode = show.seasons[0].episodes[0]
    full_hd = make_result("Example.Show.S01E01.1080p", seeders=200, score=100)
    ultra_hd = make_result("Example.Show.S01E01.2160p", seeders=2, score=1)
    job = make_job(
        kind=AutomationJobKind.episode,
        show_id=show.id,
        episode_id=episode.id,
    )
    repository = FakeAutomationRepository(job)
    tv_service = FakeTvService(
        show,
        season_releases={},
        episode_releases=[full_hd, ultra_hd],
    )
    service = make_service(repository, SimpleNamespace(), tv_service)

    status = run(service.process_job(job))

    assert status == AutomationJobStatus.succeeded
    assert tv_service.download_calls == [{episode.id}]
    assert repository.downloading_results == [ultra_hd]


def test_interactive_episode_search_excludes_packs_and_wrong_episodes() -> None:
    show = make_show()
    episode = show.seasons[0].episodes[0]
    exact = make_result("Example.Show.S01E01.1080p")
    wrong_episode = make_result("Example.Show.S01E02.2160p")
    season_pack = make_result("Example.Show.S01.2160p")
    episode_range = make_result("Example.Show.S01E01-10.2160p")
    multi_episode = make_result("Example.Show.S01E01-E02.2160p")
    wrong_show = make_result("Another.Show.S01E01.2160p")
    indexer_service = SimpleNamespace(
        search_episode=AsyncMock(
            return_value=[
                wrong_episode,
                season_pack,
                episode_range,
                multi_episode,
                wrong_show,
                exact,
            ]
        )
    )
    service = object.__new__(TvService)
    service.indexer_service = indexer_service

    results = run(service.get_episode_releases(show=show, episode_id=episode.id))

    assert results == [exact]
    indexer_service.search_episode.assert_awaited_once_with(
        show=show,
        season_number=1,
        episode_number=1,
    )


def test_missing_release_is_retried_with_exponential_backoff() -> None:
    show = make_show()
    job = make_job(
        kind=AutomationJobKind.show,
        show_id=show.id,
        attempts=3,
    )
    repository = FakeAutomationRepository(job)
    tv_service = FakeTvService(show, {})
    service = make_service(repository, SimpleNamespace(), tv_service)

    status = run(service.process_job(job))

    assert status == AutomationJobStatus.retry_wait
    assert repository.retry_arguments["retry_at"] > datetime.now(UTC)
    delay = (
        repository.retry_arguments["retry_at"] - repository.retry_arguments["now"]
    ).total_seconds()
    assert delay == 40


def test_targeted_tv_download_does_not_reassign_managed_episodes() -> None:
    show = make_show()
    first_episode = show.seasons[0].episodes[0]
    second_episode = show.seasons[0].episodes[1]
    release = make_result("Example.Show.S01.2160p")
    torrent = make_torrent(release.title)

    indexer_service = SimpleNamespace(get_result=AsyncMock(return_value=release))
    torrent_service = SimpleNamespace(
        download=AsyncMock(return_value=torrent),
        pause_download=AsyncMock(return_value=torrent),
        resume_download=AsyncMock(return_value=torrent),
    )
    tv_repository = SimpleNamespace(
        get_season_by_number=AsyncMock(return_value=show.seasons[0]),
        get_managed_episode_ids=AsyncMock(return_value={first_episode.id}),
        add_episode_file=AsyncMock(),
    )
    service = object.__new__(TvService)
    service.indexer_service = indexer_service
    service.torrent_service = torrent_service
    service.tv_repository = tv_repository

    result = run(
        service.download_torrent(
            public_indexer_result_id=release.id,
            show_id=show.id,
            episode_ids={first_episode.id, second_episode.id},
        )
    )

    assert result == torrent
    assert tv_repository.add_episode_file.await_count == 1
    added_file = tv_repository.add_episode_file.await_args.kwargs["episode_file"]
    assert added_file.episode_id == second_episode.id
