"""Hourly scan of every TV show for newly aired episodes.

The scanner reuses the existing building blocks instead of running a second
download pipeline: episode releases come from ``TvService`` (which searches the
configured indexers and applies the scoring rules), downloads go through
``TvService.download_episode_release`` (which records the episode file and
refuses episodes that are already managed), and the automation job queue is
consulted so an episode it already owns is never searched twice.

User-facing messages are Swedish because they are shown verbatim on the
scanner page; log messages stay in English like the rest of the backend.
"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.exc import IntegrityError

from media_manager.automation.repository import AutomationRepository
from media_manager.downloads.qbittorrent import QbittorrentGateway
from media_manager.episode_scanner.config import EpisodeScannerConfig
from media_manager.episode_scanner.repository import EpisodeScanRepository, utc_now
from media_manager.episode_scanner.schemas import (
    EpisodeScanItem,
    EpisodeScanOutcome,
    EpisodeScanProgress,
    EpisodeScanReason,
    EpisodeScanRun,
    EpisodeScanRunId,
    EpisodeScanRunStatus,
    EpisodeScanStatus,
    EpisodeScanTrigger,
)
from media_manager.exceptions import ConflictError, NotFoundError
from media_manager.indexer.schemas import IndexerQueryResult
from media_manager.indexer.utils import redact_secrets
from media_manager.torrent.config import TorrentConfig
from media_manager.tv.schemas import (
    Episode,
    EpisodeFileState,
    Season,
    SeasonNumber,
    Show,
)
from media_manager.tv.service import TvService

log = logging.getLogger(__name__)

# The scheduler checks whether a scan is due on this cadence (see scheduler.py).
SCHEDULER_TICK_MINUTES = 5
# Scheduled runs start a fraction of a second after a tick. Without some slack
# the next run would miss its tick and slip by a whole tick interval.
DUE_TOLERANCE = timedelta(seconds=60)

MAX_MESSAGE_LENGTH = 1000
_EPISODE_TOKEN_PATTERN = re.compile(
    r"s(?P<season>\d{1,2}) ?e(?P<first>\d{1,3})(?:(?:-?e|-)(?P<last>\d{1,3}))?(?!\d)",
    re.IGNORECASE,
)
_CROSS_EPISODE_TOKEN_PATTERN = re.compile(
    r"(?<!\d)(?P<season>\d{1,2})x(?P<first>\d{2,3})(?!\d)",
    re.IGNORECASE,
)
# A torrent name may carry a year or a country code between the show name and
# the episode token ("The.Office.US.S01E01", "Doctor.Who.2005.S01E01").
MAX_TITLE_SUFFIX_LENGTH = 6
MAX_EPISODE_RANGE = 50

NO_INDEXER_MESSAGE = (
    "Ingen indexerare är aktiverad. Aktivera Prowlarr under Settings → Downloads "
    "and indexers (eller Jackett i config.toml)."
)
NO_DOWNLOAD_CLIENT_MESSAGE = (
    "Ingen nedladdningstjänst är aktiverad. Aktivera qBittorrent under Settings → "
    "Downloads and indexers (eller Transmission/SABnzbd i config.toml)."
)
UNREACHABLE_DOWNLOAD_CLIENT_MESSAGE = (
    "Nedladdningstjänsten är aktiverad men MediaManager kunde inte ansluta till "
    "den. Kontrollera adress, port och inloggning under Settings → Downloads and "
    "indexers."
)
SCAN_ALREADY_RUNNING_MESSAGE = "En scanning pågår redan."


def redact(text: str) -> str:
    """Remove URL queries, credentials and key parameters, and cap the length."""
    text = redact_secrets(text)
    if len(text) > MAX_MESSAGE_LENGTH:
        return text[: MAX_MESSAGE_LENGTH - 1] + "…"
    return text


def describe_error(error: BaseException) -> str:
    detail = str(error).strip()
    name = type(error).__name__
    return redact(f"{name}: {detail}" if detail else name)


def next_scheduler_tick(moment: datetime) -> datetime:
    """Round ``moment`` up to the next tick the scheduler fires on."""
    moment = moment.astimezone(UTC)
    tick = moment.replace(second=0, microsecond=0)
    remainder = tick.minute % SCHEDULER_TICK_MINUTES
    if remainder == 0 and tick == moment:
        return tick
    return tick + timedelta(minutes=SCHEDULER_TICK_MINUTES - remainder)


def compute_next_scan_at(
    *,
    enabled: bool,
    interval: timedelta,
    last_started_at: datetime | None,
    now: datetime,
) -> datetime | None:
    """Return when the scheduler will start the next automatic scan."""
    if not enabled:
        return None
    if last_started_at is None:
        due = now
    else:
        due = max(last_started_at + interval - DUE_TOLERANCE, now)
    return next_scheduler_tick(due)


def _normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def torrent_matches_episode(
    torrent_name: str,
    *,
    show_name: str,
    season_number: int,
    episode_number: int,
) -> bool:
    """Heuristically decide whether a download-client torrent is this episode.

    Only single episodes and explicit multi-episode ranges match; season packs
    are ignored because they rarely contain an episode that just aired.
    """
    normalized_show = _normalize_title(show_name)
    if not normalized_show:
        return False
    name = re.sub(r"[._]+", " ", torrent_name)
    for pattern in (_EPISODE_TOKEN_PATTERN, _CROSS_EPISODE_TOKEN_PATTERN):
        for match in pattern.finditer(name):
            prefix = _normalize_title(name[: match.start()])
            if not prefix.startswith(normalized_show):
                continue
            if len(prefix) - len(normalized_show) > MAX_TITLE_SUFFIX_LENGTH:
                continue
            if int(match.group("season")) != season_number:
                continue
            first = int(match.group("first"))
            last_group = match.groupdict().get("last")
            last = int(last_group) if last_group else first
            if last < first or last - first > MAX_EPISODE_RANGE:
                last = first
            if first <= episode_number <= last:
                return True
    return False


class EpisodeScanService:
    """Status, settings and scheduling for the scanner.

    This class deliberately has no indexer or download-client dependencies so
    the frequent due-check and the status page stay cheap.
    """

    def __init__(
        self,
        repository: EpisodeScanRepository,
        config: EpisodeScannerConfig | None = None,
    ) -> None:
        self.repository = repository
        self.config = config or EpisodeScannerConfig()

    @property
    def interval(self) -> timedelta:
        return timedelta(minutes=self.config.interval_minutes)

    async def get_status(self) -> EpisodeScanStatus:
        now = utc_now()
        await self.repository.recover_stale_runs(
            lease_timeout_seconds=self.config.lease_timeout_seconds,
            now=now,
        )
        settings = await self.repository.get_settings()
        recent_runs = await self.repository.list_runs(limit=10)
        latest_run = recent_runs[0] if recent_runs else None
        latest_items = (
            await self.repository.list_items(latest_run.id) if latest_run else []
        )
        recent_sent = await self.repository.list_recent_items(
            EpisodeScanOutcome.sent,
            limit=25,
        )
        return EpisodeScanStatus(
            enabled=settings.enabled,
            interval_minutes=self.config.interval_minutes,
            lookback_days=self.config.lookback_days,
            running=(
                latest_run is not None
                and latest_run.status == EpisodeScanRunStatus.running
            ),
            next_scan_at=compute_next_scan_at(
                enabled=settings.enabled,
                interval=self.interval,
                last_started_at=latest_run.started_at if latest_run else None,
                now=now,
            ),
            server_time=now,
            latest_run=latest_run,
            latest_items=latest_items,
            recent_sent=recent_sent,
            recent_runs=recent_runs,
        )

    async def set_enabled(self, enabled: bool) -> EpisodeScanStatus:
        await self.repository.set_enabled(enabled)
        log.info("Automatic episode scanning %s", "enabled" if enabled else "disabled")
        return await self.get_status()

    async def start_manual_scan(self) -> EpisodeScanRun:
        """Create a manual run; manual scans work even when automation is off."""
        await self.repository.recover_stale_runs(
            lease_timeout_seconds=self.config.lease_timeout_seconds,
        )
        run = await self.repository.create_run(EpisodeScanTrigger.manual)
        if run is None:
            raise ConflictError(SCAN_ALREADY_RUNNING_MESSAGE)
        return run

    async def start_scheduled_scan_if_due(
        self,
        *,
        now: datetime | None = None,
    ) -> EpisodeScanRun | None:
        current_time = now or utc_now()
        settings = await self.repository.get_settings()
        if not settings.enabled:
            return None
        await self.repository.recover_stale_runs(
            lease_timeout_seconds=self.config.lease_timeout_seconds,
            now=current_time,
        )
        latest_run = await self.repository.get_latest_run()
        if latest_run is not None:
            if latest_run.status == EpisodeScanRunStatus.running:
                return None
            due_at = latest_run.started_at + self.interval - DUE_TOLERANCE
            if current_time < due_at:
                return None
        return await self.repository.create_run(
            EpisodeScanTrigger.scheduled,
            now=current_time,
        )

    async def mark_start_failed(
        self,
        run_id: EpisodeScanRunId,
        error: BaseException,
    ) -> None:
        await self.repository.finish_run(
            run_id,
            status=EpisodeScanRunStatus.failed,
            progress=EpisodeScanProgress(),
            message=(f"Bakgrundsjobbet kunde inte startas: {describe_error(error)}"),
        )


class _LeaseLostError(RuntimeError):
    """The run stopped being "running" (e.g. marked interrupted) mid-scan."""


@dataclass
class _ScanContext:
    configuration_error: str | None = None
    notes: list[str] = field(default_factory=list)
    accepts_torrents: bool = False
    accepts_usenet: bool = False
    client_torrent_names: list[str] | None = None


class EpisodeScanRunner:
    """Executes one scan run: every show is checked, one failure never stops it."""

    def __init__(
        self,
        repository: EpisodeScanRepository,
        tv_service: TvService,
        automation_repository: AutomationRepository,
        config: EpisodeScannerConfig | None = None,
        torrent_config: TorrentConfig | None = None,
        qbittorrent_gateway_factory: Callable[[], QbittorrentGateway] | None = None,
        lease_keeper: Callable[[EpisodeScanRunId], Awaitable[bool]] | None = None,
    ) -> None:
        self.repository = repository
        self.tv_service = tv_service
        self.automation_repository = automation_repository
        self.config = config or EpisodeScannerConfig()
        self.torrent_config = torrent_config
        self.qbittorrent_gateway_factory = qbittorrent_gateway_factory
        # Renews the run's lease from its own database session while a slow
        # indexer search keeps the scan itself busy. Without one, the lease is
        # only renewed between shows and episodes.
        self.lease_keeper = lease_keeper
        self._lease_lost = False

    async def execute(self, run_id: EpisodeScanRunId) -> EpisodeScanRun | None:
        try:
            run = await self.repository.get_run(run_id)
        except NotFoundError:
            log.warning("Episode scan %s no longer exists; nothing to do", run_id)
            return None
        if run.status != EpisodeScanRunStatus.running:
            log.info(
                "Episode scan %s is already %s; not starting it again",
                run_id,
                run.status,
            )
            return run

        log.info("Starting %s episode scan %s", run.trigger, run_id)
        keep_alive = (
            asyncio.create_task(self._keep_alive(run_id))
            if self.lease_keeper is not None
            else None
        )
        try:
            return await self._execute_running(run_id)
        finally:
            if keep_alive is not None:
                keep_alive.cancel()
                try:
                    await keep_alive
                except asyncio.CancelledError:
                    pass

    async def _execute_running(self, run_id: EpisodeScanRunId) -> EpisodeScanRun:
        progress = EpisodeScanProgress()
        context = _ScanContext()
        try:
            await self._save_progress(run_id, progress)
            context = await self._build_context()
            shows = sorted(
                await self.tv_service.get_all_shows(),
                key=lambda show: show.name.casefold(),
            )
            progress.shows_total = len(shows)
            await self._save_progress(run_id, progress)
            for show in shows:
                await self._scan_show_safely(run_id, show, context, progress)
                await self._save_progress(run_id, progress)
        except _LeaseLostError:
            log.warning(
                "Episode scan %s is no longer marked as running; stopping it",
                run_id,
            )
            return await self.repository.get_run(run_id)
        except Exception as error:
            log.exception("Episode scan %s failed", run_id)
            await self.repository.rollback()
            finished = await self.repository.finish_run(
                run_id,
                status=EpisodeScanRunStatus.failed,
                progress=progress,
                message=f"Scanningen avbröts av ett fel: {describe_error(error)}",
            )
        else:
            finished = await self.repository.finish_run(
                run_id,
                status=(
                    EpisodeScanRunStatus.succeeded
                    if progress.errors == 0
                    else EpisodeScanRunStatus.completed_with_errors
                ),
                progress=progress,
                message=self._summary_message(context),
            )
        await self._prune_history()
        log.info(
            "Episode scan %s finished as %s: shows=%d/%d sent=%d skipped=%d "
            "not_found=%d errors=%d",
            run_id,
            finished.status,
            progress.shows_checked,
            progress.shows_total,
            progress.episodes_sent,
            progress.episodes_skipped,
            progress.episodes_not_found,
            progress.errors,
        )
        return finished

    async def _build_context(self) -> _ScanContext:
        context = _ScanContext()
        problems: list[str] = []
        if not self.tv_service.indexer_service.indexers:
            problems.append(NO_INDEXER_MESSAGE)

        download_manager = self.tv_service.torrent_service.download_manager
        context.accepts_torrents = download_manager.has_torrent_client
        context.accepts_usenet = download_manager.has_usenet_client
        if not (context.accepts_torrents or context.accepts_usenet):
            problems.append(self._download_client_problem())
        context.configuration_error = " ".join(problems) or None

        if (
            self.torrent_config is not None
            and self.torrent_config.qbittorrent.enabled
            and context.accepts_torrents
        ):
            try:
                context.client_torrent_names = await asyncio.to_thread(
                    self._qbittorrent_gateway().torrent_names
                )
            except Exception as error:
                log.warning(
                    "Could not list qBittorrent torrents for duplicate detection (%s)",
                    type(error).__name__,
                )
                context.notes.append(
                    "Kunde inte läsa torrentlistan i qBittorrent, så dubbletter som "
                    "lagts till direkt i qBittorrent kunde inte upptäckas: "
                    f"{describe_error(error)}"
                )
        return context

    async def _keep_alive(self, run_id: EpisodeScanRunId) -> None:
        if self.lease_keeper is None:
            return
        while True:
            await asyncio.sleep(self.config.heartbeat_seconds)
            try:
                still_running = await self.lease_keeper(run_id)
            except Exception:
                log.warning(
                    "Could not renew the lease of episode scan %s",
                    run_id,
                    exc_info=True,
                )
                continue
            if not still_running:
                self._lease_lost = True
                return

    async def _save_progress(
        self,
        run_id: EpisodeScanRunId,
        progress: EpisodeScanProgress,
    ) -> None:
        if self._lease_lost or not await self.repository.save_progress(
            run_id, progress
        ):
            raise _LeaseLostError

    def _download_client_problem(self) -> str:
        config = self.torrent_config
        if config is not None and (
            config.qbittorrent.enabled
            or config.transmission.enabled
            or config.sabnzbd.enabled
        ):
            return UNREACHABLE_DOWNLOAD_CLIENT_MESSAGE
        return NO_DOWNLOAD_CLIENT_MESSAGE

    def _qbittorrent_gateway(self) -> QbittorrentGateway:
        if self.qbittorrent_gateway_factory is not None:
            return self.qbittorrent_gateway_factory()
        if self.torrent_config is None:
            msg = "No qBittorrent configuration is available."
            raise RuntimeError(msg)
        return QbittorrentGateway(self.torrent_config.qbittorrent)

    @staticmethod
    def _summary_message(context: _ScanContext) -> str | None:
        parts = [*context.notes]
        if context.configuration_error:
            parts.insert(0, context.configuration_error)
        return "\n".join(parts) or None

    async def _scan_show_safely(
        self,
        run_id: EpisodeScanRunId,
        show: Show,
        context: _ScanContext,
        progress: EpisodeScanProgress,
    ) -> None:
        try:
            await self._scan_show(run_id, show, context, progress)
        except _LeaseLostError:
            raise
        except Exception as error:
            log.exception("Episode scan %s failed for show %s", run_id, show.name)
            await self.repository.rollback()
            progress.shows_failed += 1
            await self._record(
                progress,
                EpisodeScanItem(
                    run_id=run_id,
                    show_id=show.id,
                    show_name=show.name,
                    outcome=EpisodeScanOutcome.error,
                    reason=EpisodeScanReason.unexpected,
                    message=describe_error(error),
                ),
            )
        else:
            progress.shows_checked += 1

    async def _scan_show(
        self,
        run_id: EpisodeScanRunId,
        show: Show,
        context: _ScanContext,
        progress: EpisodeScanProgress,
    ) -> None:
        candidates = self.new_episodes(show, today=utc_now().date())
        if not candidates:
            return

        file_states = await self.tv_service.tv_repository.get_episode_file_states(
            show.id
        )
        (
            queued_episode_ids,
            show_job_active,
        ) = await self.automation_repository.get_pending_show_targets(show.id)
        monitored = self.show_is_monitored(show)

        for season, episode in candidates:
            state = file_states.get(episode.id)
            reason: EpisodeScanReason | None = None
            if state == EpisodeFileState.IN_LIBRARY:
                reason = EpisodeScanReason.in_library
            elif state == EpisodeFileState.DOWNLOADING:
                reason = EpisodeScanReason.downloading
            elif not monitored:
                reason = EpisodeScanReason.not_monitored
            elif not season.monitored:
                reason = EpisodeScanReason.season_not_monitored
            elif episode.id in queued_episode_ids or show_job_active:
                reason = EpisodeScanReason.queued
            elif self._in_download_client(context, show, season, episode):
                reason = EpisodeScanReason.in_download_client

            if reason is not None:
                await self._record(
                    progress,
                    self._episode_item(
                        run_id,
                        show,
                        season,
                        episode,
                        outcome=EpisodeScanOutcome.skipped,
                        reason=reason,
                    ),
                )
                continue

            if context.configuration_error:
                await self._record(
                    progress,
                    self._episode_item(
                        run_id,
                        show,
                        season,
                        episode,
                        outcome=EpisodeScanOutcome.error,
                        reason=EpisodeScanReason.configuration,
                        message=context.configuration_error,
                    ),
                )
                continue

            await self._search_and_send(
                run_id, show, season, episode, context, progress
            )
            # Searches can be slow; publish progress after every one.
            await self._save_progress(run_id, progress)

    def new_episodes(self, show: Show, *, today: date) -> list[tuple[Season, Episode]]:
        """Episodes that aired within the look-back window, oldest first."""
        window_start = today - timedelta(days=self.config.lookback_days)
        candidates: list[tuple[Season, Episode]] = []
        for season in sorted(show.seasons, key=lambda season: season.number):
            if season.number == SeasonNumber(0) and not self.config.include_specials:
                continue
            for episode in sorted(season.episodes, key=lambda episode: episode.number):
                # An unknown date is not proof that the episode has aired.
                if episode.air_date is None:
                    continue
                if window_start <= episode.air_date <= today:
                    candidates.append((season, episode))
        return candidates

    @staticmethod
    def show_is_monitored(show: Show) -> bool:
        if show.continuous_download:
            return True
        # A metadata refresh switches continuous download off as soon as the
        # provider marks a show as ended, which is often right at its finale.
        # Seasons stay monitored, so keep fetching the final recent episodes.
        return show.ended and any(season.monitored for season in show.seasons)

    def _in_download_client(
        self,
        context: _ScanContext,
        show: Show,
        season: Season,
        episode: Episode,
    ) -> bool:
        if not context.client_torrent_names:
            return False
        return any(
            torrent_matches_episode(
                name,
                show_name=show.name,
                season_number=int(season.number),
                episode_number=int(episode.number),
            )
            for name in context.client_torrent_names
        )

    def _accepts(self, context: _ScanContext, release: IndexerQueryResult) -> bool:
        return context.accepts_usenet if release.usenet else context.accepts_torrents

    async def _search_and_send(
        self,
        run_id: EpisodeScanRunId,
        show: Show,
        season: Season,
        episode: Episode,
        context: _ScanContext,
        progress: EpisodeScanProgress,
    ) -> None:
        indexer_service = self.tv_service.indexer_service
        indexer_service.pop_search_errors()
        try:
            releases = await self.tv_service.get_episode_releases(
                show=show,
                episode_id=episode.id,
            )
        except Exception as error:
            log.exception(
                "Episode scan search failed for %s S%02dE%02d",
                show.name,
                season.number,
                episode.number,
            )
            await self.repository.rollback()
            await self._record(
                progress,
                self._episode_item(
                    run_id,
                    show,
                    season,
                    episode,
                    outcome=EpisodeScanOutcome.error,
                    reason=EpisodeScanReason.search,
                    message=describe_error(error),
                ),
            )
            return

        search_errors = [redact(error) for error in indexer_service.pop_search_errors()]
        releases = [release for release in releases if self._accepts(context, release)]
        if not releases:
            await self._record(
                progress,
                self._episode_item(
                    run_id,
                    show,
                    season,
                    episode,
                    outcome=(
                        EpisodeScanOutcome.error
                        if search_errors
                        else EpisodeScanOutcome.not_found
                    ),
                    reason=EpisodeScanReason.search if search_errors else None,
                    message="; ".join(search_errors) or None,
                ),
            )
            return

        selected = releases[0]
        try:
            await self.tv_service.download_episode_release(
                show=show,
                episode_id=episode.id,
                result_id=selected.id,
            )
        except (ConflictError, IntegrityError) as error:
            await self.repository.rollback()
            file_states = await self.tv_service.tv_repository.get_episode_file_states(
                show.id
            )
            if episode.id in file_states:
                item = self._episode_item(
                    run_id,
                    show,
                    season,
                    episode,
                    outcome=EpisodeScanOutcome.skipped,
                    reason=EpisodeScanReason.downloading,
                    message=(
                        "En annan nedladdning tog hand om avsnittet medan "
                        "scanningen pågick."
                    ),
                )
            else:
                item = self._episode_item(
                    run_id,
                    show,
                    season,
                    episode,
                    outcome=EpisodeScanOutcome.error,
                    reason=EpisodeScanReason.download,
                    release_title=selected.title,
                    indexer=selected.indexer,
                    message=describe_error(error),
                )
            await self._record(progress, item)
            return
        except Exception as error:
            log.exception(
                "Episode scan could not submit %s for %s S%02dE%02d",
                selected.title,
                show.name,
                season.number,
                episode.number,
            )
            await self.repository.rollback()
            await self._record(
                progress,
                self._episode_item(
                    run_id,
                    show,
                    season,
                    episode,
                    outcome=EpisodeScanOutcome.error,
                    reason=EpisodeScanReason.download,
                    release_title=selected.title,
                    indexer=selected.indexer,
                    message=describe_error(error),
                ),
            )
            return

        log.info(
            "Episode scan sent %s for %s S%02dE%02d to the download client",
            selected.title,
            show.name,
            season.number,
            episode.number,
        )
        await self._record(
            progress,
            self._episode_item(
                run_id,
                show,
                season,
                episode,
                outcome=EpisodeScanOutcome.sent,
                release_title=selected.title,
                indexer=selected.indexer,
                # Other indexers may still have failed while one found a release.
                message="; ".join(search_errors) or None,
            ),
        )

    @staticmethod
    def _episode_item(
        run_id: EpisodeScanRunId,
        show: Show,
        season: Season,
        episode: Episode,
        *,
        outcome: EpisodeScanOutcome,
        reason: EpisodeScanReason | None = None,
        release_title: str | None = None,
        indexer: str | None = None,
        message: str | None = None,
    ) -> EpisodeScanItem:
        return EpisodeScanItem(
            run_id=run_id,
            show_id=show.id,
            episode_id=episode.id,
            show_name=show.name,
            season_number=int(season.number),
            episode_number=int(episode.number),
            episode_title=episode.title,
            air_date=episode.air_date,
            outcome=outcome,
            reason=reason,
            release_title=release_title,
            indexer=indexer,
            message=message,
        )

    async def _record(
        self,
        progress: EpisodeScanProgress,
        item: EpisodeScanItem,
    ) -> None:
        await self.repository.add_item(item)
        progress.record(item.outcome, episode=item.episode_id is not None)

    async def _prune_history(self) -> None:
        cutoff = utc_now() - timedelta(days=self.config.history_days)
        try:
            await self.repository.delete_runs_started_before(cutoff)
        except Exception:
            log.exception("Could not prune old episode scan history")
            await self.repository.rollback()
