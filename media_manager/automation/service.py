import logging
from datetime import UTC, datetime, timedelta
from typing import assert_never

from sqlalchemy.exc import IntegrityError

from media_manager.automation.config import AutomationConfig
from media_manager.automation.exceptions import NoApprovedReleaseFoundError
from media_manager.automation.repository import AutomationRepository, utc_now
from media_manager.automation.schemas import (
    AutomationCycleResult,
    AutomationJob,
    AutomationJobId,
    AutomationJobKind,
    AutomationJobStatus,
)
from media_manager.exceptions import ConflictError, NotFoundError
from media_manager.indexer.schemas import IndexerQueryResult
from media_manager.indexer.utils import evaluate_indexer_query_results
from media_manager.movies.schemas import Movie
from media_manager.movies.service import MovieService
from media_manager.torrent.config import TorrentConfig
from media_manager.tv.schemas import (
    EpisodeId,
    EpisodeNumber,
    SeasonNumber,
    Show,
    ShowId,
)
from media_manager.tv.service import TvService

log = logging.getLogger(__name__)


class AutomationService:
    """Coordinates indexer searches and idempotent media downloads."""

    def __init__(
        self,
        repository: AutomationRepository,
        movie_service: MovieService,
        tv_service: TvService,
        config: AutomationConfig | None = None,
        torrent_config: TorrentConfig | None = None,
    ) -> None:
        self.repository = repository
        self.movie_service = movie_service
        self.tv_service = tv_service
        self.config = config or AutomationConfig()
        self.torrent_config = torrent_config

    async def get_job(self, job_id: AutomationJobId) -> AutomationJob:
        return await self.repository.get_job(job_id)

    async def list_jobs(
        self,
        *,
        status: AutomationJobStatus | None = None,
        kind: AutomationJobKind | None = None,
        show_id: ShowId | None = None,
        episode_id: EpisodeId | None = None,
        limit: int = 100,
    ) -> list[AutomationJob]:
        return await self.repository.list_jobs(
            status=status,
            kind=kind,
            show_id=show_id,
            episode_id=episode_id,
            limit=limit,
        )

    async def retry_job(self, job_id: AutomationJobId) -> AutomationJob:
        return await self.repository.retry_job(job_id)

    async def enqueue_movie(
        self,
        movie: Movie,
        *,
        force: bool = False,
    ) -> AutomationJob | None:
        if not self.config.enabled or (
            not force and not self.config.auto_download_movies
        ):
            return None
        if await self.movie_service.movie_repository.has_movie_file(movie.id):
            return None
        job, _ = await self.repository.enqueue_movie(movie.id, force=force)
        return job

    async def enqueue_show(
        self,
        show: Show,
        *,
        force: bool = False,
    ) -> AutomationJob | None:
        if not self.config.enabled or not self.config.auto_download_shows:
            return None
        # A show may exist in the library without being monitored. Keep the
        # guard here as well as in the worker so an unmonitored add never causes
        # indexer or download-client traffic.
        if not force and not show.continuous_download:
            return None
        if not self._eligible_episode_ids(show):
            return None
        managed = await self.tv_service.tv_repository.get_managed_episode_ids(show.id)
        if self._eligible_episode_ids(show).issubset(managed):
            return None
        job, _ = await self.repository.enqueue_show(show.id, force=force)
        return job

    async def enqueue_episode(
        self,
        show: Show,
        episode_id: EpisodeId,
        *,
        force: bool = True,
    ) -> AutomationJob:
        """Persist an explicit row-level automatic search.

        This action is user initiated, so it remains available when autonomous
        library scanning is disabled in configuration.
        """
        if episode_id not in self._episode_locations(show):
            msg = f"Episode {episode_id} does not belong to show {show.id}."
            raise NotFoundError(msg)
        managed = await self.tv_service.tv_repository.get_managed_episode_ids(show.id)
        if episode_id in managed:
            msg = f"Episode {episode_id} is already imported or assigned to a download."
            raise ConflictError(msg)
        job, _ = await self.repository.enqueue_episode(
            show.id,
            episode_id,
            force=force,
        )
        return job

    async def queue_missing_movies(self) -> int:
        """Queue unclaimed movies, including ones added while workers were offline."""
        if not self.config.enabled or not self.config.auto_download_movies:
            return 0
        queued = 0
        for movie in await self.movie_service.get_all_movies():
            if await self.movie_service.movie_repository.has_movie_file(movie.id):
                continue
            _, was_queued = await self.repository.enqueue_movie(movie.id)
            queued += int(was_queued)
        return queued

    async def queue_continuous_downloads(self) -> int:
        """Queue opted-in shows when metadata contains unmanaged episodes."""
        if (
            not self.config.enabled
            or not self.config.auto_download_shows
            or not self.config.continuous_download_enabled
        ):
            return 0
        queued = 0
        shows = await self.tv_service.tv_repository.get_continuous_download_shows()
        for show in shows:
            eligible = self._eligible_episode_ids(show)
            if not eligible:
                continue
            managed = await self.tv_service.tv_repository.get_managed_episode_ids(
                show.id
            )
            if eligible.issubset(managed):
                continue
            _, was_queued = await self.repository.enqueue_show(show.id)
            queued += int(was_queued)
        return queued

    async def run_automation_cycle(self) -> AutomationCycleResult:
        """Taskiq-compatible entry point for scanning and processing due jobs."""
        result = AutomationCycleResult()
        if self.config.enabled:
            result.queued += await self.queue_missing_movies()
            result.queued += await self.queue_continuous_downloads()
        kinds = (
            None
            if self.config.enabled
            else frozenset({AutomationJobKind.episode})
        )
        processed = await self.process_due_jobs(kinds=kinds)
        processed.queued = result.queued
        return processed

    async def process_due_jobs(
        self,
        *,
        kinds: frozenset[AutomationJobKind] | None = None,
    ) -> AutomationCycleResult:
        """Claim and process jobs one at a time, up to the configured batch size.

        A lease starts when a job is claimed. Claiming the whole batch up front can
        therefore expire the lease of later jobs while an earlier, slow indexer
        search is still running. Keeping only one claimed job outstanding makes
        the lease describe work that is actually in progress.
        """
        result = AutomationCycleResult()

        for _ in range(self.config.process_batch_size):
            jobs = await self.repository.claim_due_jobs(
                limit=1,
                lease_timeout_seconds=self.config.lease_timeout_seconds,
                kinds=kinds,
            )
            if not jobs:
                break

            job = jobs[0]
            result.claimed += 1
            result.job_ids.append(job.id)
            final_status = await self.process_job(job)
            if final_status == AutomationJobStatus.succeeded:
                result.succeeded += 1
            elif final_status == AutomationJobStatus.skipped:
                result.skipped += 1
            elif final_status == AutomationJobStatus.retry_wait:
                result.retrying += 1
            elif final_status == AutomationJobStatus.failed:
                result.failed += 1
        return result

    async def process_job(self, job: AutomationJob) -> AutomationJobStatus:
        """Process a previously claimed job and persist its final state."""
        try:
            if job.kind == AutomationJobKind.movie:
                await self._process_movie(job)
            elif job.kind == AutomationJobKind.show:
                await self._process_show(job)
            elif job.kind == AutomationJobKind.episode:
                await self._process_episode(job)
            else:
                assert_never(job.kind)
        except NotFoundError:
            log.warning("Automation target for job %s no longer exists", job.id)
            try:
                finished = await self.repository.mark_skipped(
                    job.id,
                    message="The media item was deleted before processing.",
                )
            except NotFoundError:
                # The target's ON DELETE CASCADE may have removed the job too.
                return AutomationJobStatus.skipped
            return finished.status
        except Exception as error:
            log.exception("Automatic download job %s failed", job.id)
            return await self._schedule_retry(job, error)
        updated = await self.repository.get_job(job.id)
        return updated.status

    async def _process_movie(self, job: AutomationJob) -> None:
        if job.movie_id is None:
            msg = f"Movie automation job {job.id} has no movie id."
            raise RuntimeError(msg)
        movie = await self.movie_service.get_movie_by_id(job.movie_id)
        if await self.movie_service.movie_repository.has_movie_file(movie.id):
            await self.repository.mark_skipped(
                job.id,
                message="Movie is already imported or assigned to a download.",
            )
            return

        releases = await self.movie_service.get_all_available_torrents_for_movie(movie)
        releases = self._deduplicate_releases(releases)
        if not releases:
            msg = f"No approved release found for {movie.name} ({movie.year})."
            raise NoApprovedReleaseFoundError(msg)

        selected = releases[0]
        try:
            torrent = await self.movie_service.download_torrent(
                public_indexer_result_id=selected.id,
                movie=movie,
            )
        except IntegrityError:
            if await self.movie_service.movie_repository.has_movie_file(movie.id):
                await self.repository.mark_skipped(
                    job.id,
                    message="Another operation already assigned this movie.",
                )
                return
            raise

        await self.repository.mark_downloading(
            job.id,
            result=selected,
            torrent=torrent,
        )
        await self.repository.mark_succeeded(
            job.id,
            message=f"Submitted {selected.title} to the download client.",
        )

    async def _process_show(self, job: AutomationJob) -> None:
        if job.show_id is None:
            msg = f"Show automation job {job.id} has no show id."
            raise RuntimeError(msg)
        show = await self.tv_service.get_show_by_id(job.show_id)
        # The user may unmonitor a show after its job was queued. Re-check the
        # persisted state immediately before any Prowlarr search/qBittorrent
        # submission to close that race safely.
        if not show.continuous_download:
            await self.repository.mark_skipped(
                job.id,
                message="Show is no longer monitored.",
            )
            return
        remaining = await self._get_unmanaged_episode_ids(show)
        if not remaining:
            await self.repository.mark_skipped(
                job.id,
                message="All eligible episodes are imported or assigned to downloads.",
            )
            return

        episode_locations = self._episode_locations(show)
        release_cache: dict[int, list[IndexerQueryResult]] = {}
        submitted_releases = 0

        while remaining:
            if submitted_releases >= self.config.max_releases_per_show_cycle:
                msg = (
                    f"Show {show.name} still has {len(remaining)} unmanaged episodes "
                    "after reaching the per-cycle release limit."
                )
                raise RuntimeError(msg)

            target_id = min(
                remaining,
                key=lambda episode_id: episode_locations[episode_id],
            )
            season_number, episode_number = episode_locations[target_id]
            releases = release_cache.get(season_number)
            if releases is None:
                releases = await self._search_show_season(
                    show,
                    season_number=season_number,
                )
                release_cache[season_number] = releases

            matching = [
                release
                for release in releases
                if target_id in self._release_episode_ids(release, show, remaining)
            ]
            if not matching:
                matching = await self._search_show_episode(
                    show,
                    season_number=season_number,
                    episode_number=episode_number,
                )
                matching = [
                    release
                    for release in matching
                    if target_id in self._release_episode_ids(release, show, remaining)
                ]
            if not matching:
                msg = (
                    f"No approved release found for {show.name} "
                    f"S{season_number:02d}E{episode_number:02d}."
                )
                raise NoApprovedReleaseFoundError(msg)

            selected = matching[0]
            covered = self._release_episode_ids(selected, show, remaining)
            if not covered:
                msg = f"Selected release {selected.title} covers no missing episodes."
                raise RuntimeError(msg)

            try:
                torrent = await self.tv_service.download_torrent(
                    public_indexer_result_id=selected.id,
                    show_id=show.id,
                    episode_ids=covered,
                )
            except ConflictError:
                refreshed_remaining = await self._get_unmanaged_episode_ids(show)
                if refreshed_remaining == remaining:
                    raise
                remaining = refreshed_remaining
                continue

            submitted_releases += 1
            await self.repository.mark_downloading(
                job.id,
                result=selected,
                torrent=torrent,
                message=(
                    f"Submitted {selected.title}; it covers {len(covered)} "
                    "previously unmanaged episode(s)."
                ),
            )
            refreshed_remaining = await self._get_unmanaged_episode_ids(show)
            if refreshed_remaining == remaining:
                msg = (
                    f"Release {selected.title} was submitted but no episode "
                    "association was created."
                )
                raise RuntimeError(msg)
            remaining = refreshed_remaining

        await self.repository.mark_succeeded(
            job.id,
            message=(
                f"Submitted {submitted_releases} release(s); all eligible episodes "
                "are now managed."
            ),
        )

    async def _process_episode(self, job: AutomationJob) -> None:
        if job.show_id is None or job.episode_id is None:
            msg = f"Episode automation job {job.id} has no complete target."
            raise RuntimeError(msg)

        show = await self.tv_service.get_show_by_id(job.show_id)
        location = self._episode_locations(show).get(job.episode_id)
        if location is None:
            msg = f"Episode {job.episode_id} does not belong to show {show.id}."
            raise NotFoundError(msg)

        managed = await self.tv_service.tv_repository.get_managed_episode_ids(show.id)
        if job.episode_id in managed:
            await self.repository.mark_skipped(
                job.id,
                message="Episode is already imported or assigned to a download.",
            )
            return

        season_number, episode_number = location
        releases = await self.tv_service.get_episode_releases(
            show=show,
            episode_id=job.episode_id,
        )
        releases = self._deduplicate_releases(releases)
        if not releases:
            msg = (
                f"No approved release found for {show.name} "
                f"S{season_number:02d}E{episode_number:02d}."
            )
            raise NoApprovedReleaseFoundError(msg)

        selected = releases[0]
        try:
            torrent = await self.tv_service.download_episode_release(
                show=show,
                episode_id=job.episode_id,
                result_id=selected.id,
            )
        except ConflictError:
            managed = await self.tv_service.tv_repository.get_managed_episode_ids(
                show.id
            )
            if job.episode_id not in managed:
                raise
            await self.repository.mark_skipped(
                job.id,
                message="Another operation already assigned this episode.",
            )
            return

        await self.repository.mark_downloading(
            job.id,
            result=selected,
            torrent=torrent,
            message=(
                f"Submitted {selected.title} for "
                f"S{season_number:02d}E{episode_number:02d}."
            ),
        )
        await self.repository.mark_succeeded(
            job.id,
            message=(
                f"Submitted {selected.title} to the configured download client."
            ),
        )

    async def _search_show_season(
        self,
        show: Show,
        *,
        season_number: int,
    ) -> list[IndexerQueryResult]:
        releases = await self.tv_service.get_all_available_torrents_for_a_season(
            season_number=season_number,
            show_id=show.id,
        )
        return self._deduplicate_releases(releases)

    async def _search_show_episode(
        self,
        show: Show,
        *,
        season_number: int,
        episode_number: int,
    ) -> list[IndexerQueryResult]:
        releases = await self.tv_service.indexer_service.search_episode(
            show=show,
            season_number=season_number,
            episode_number=episode_number,
        )
        releases = [
            release
            for release in releases
            if season_number in release.season
            and episode_number in release.episode
        ]
        releases = evaluate_indexer_query_results(
            releases,
            media=show,
            is_tv=True,
        )
        return self._deduplicate_releases(releases)

    async def _get_unmanaged_episode_ids(self, show: Show) -> set[EpisodeId]:
        eligible = self._eligible_episode_ids(show)
        managed = await self.tv_service.tv_repository.get_managed_episode_ids(show.id)
        return eligible - managed

    def _eligible_episode_ids(self, show: Show) -> set[EpisodeId]:
        today = datetime.now(UTC).date()
        return {
            episode.id
            for season in show.seasons
            if self.config.include_specials or season.number != SeasonNumber(0)
            if season.monitored
            for episode in season.episodes
            # Unknown dates are not proof that an episode has aired. Waiting for
            # a concrete provider date prevents premature/bulk downloads.
            if episode.air_date is not None and episode.air_date <= today
        }

    @staticmethod
    def _episode_locations(show: Show) -> dict[EpisodeId, tuple[int, int]]:
        return {
            episode.id: (int(season.number), int(episode.number))
            for season in show.seasons
            for episode in season.episodes
        }

    def _release_episode_ids(
        self,
        release: IndexerQueryResult,
        show: Show,
        candidates: set[EpisodeId],
    ) -> set[EpisodeId]:
        release_seasons = set(release.season)
        release_episodes = {EpisodeNumber(number) for number in release.episode}
        covered: set[EpisodeId] = set()
        for season in show.seasons:
            if int(season.number) not in release_seasons:
                continue
            if not self.config.include_specials and season.number == SeasonNumber(0):
                continue
            for episode in season.episodes:
                if episode.id not in candidates:
                    continue
                if release_episodes and episode.number not in release_episodes:
                    continue
                covered.add(episode.id)
        return covered

    def _deduplicate_releases(
        self,
        releases: list[IndexerQueryResult],
    ) -> list[IndexerQueryResult]:
        compatible_releases = [
            release for release in releases if self._has_download_client(release)
        ]
        compatible_releases.sort(reverse=True)
        unique: list[IndexerQueryResult] = []
        seen: set[tuple[str, int, bool]] = set()
        for release in compatible_releases:
            key = (release.title.casefold().strip(), release.size, release.usenet)
            if key in seen:
                continue
            seen.add(key)
            unique.append(release)
        return unique

    def _has_download_client(self, release: IndexerQueryResult) -> bool:
        """Return whether the configured clients can accept this release type."""
        if self.torrent_config is None:
            # Keeps the service independently testable; the application dependency
            # always provides the real download-client configuration.
            return True
        if release.usenet:
            return self.torrent_config.sabnzbd.enabled
        return (
            self.torrent_config.qbittorrent.enabled
            or self.torrent_config.transmission.enabled
        )

    async def _schedule_retry(
        self,
        job: AutomationJob,
        error: Exception,
    ) -> AutomationJobStatus:
        current_time = utc_now()
        exponent = max(job.attempts - 1, 0)
        delay_seconds = min(
            self.config.base_backoff_seconds * (2**exponent),
            self.config.max_backoff_seconds,
        )
        retry_at = current_time + timedelta(seconds=delay_seconds)
        exhausted_retry_at = current_time + timedelta(
            seconds=self.config.exhausted_retry_seconds
        )
        error_message = f"{type(error).__name__}: {error}"[:8000]
        updated = await self.repository.mark_retry_or_failed(
            job.id,
            error=error_message,
            max_attempts=self.config.max_attempts,
            retry_at=retry_at,
            exhausted_retry_at=exhausted_retry_at,
            now=current_time,
        )
        return updated.status
