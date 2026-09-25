import logging
from urllib.parse import quote
from uuid import UUID

import taskiq_fastapi
from taskiq import TaskiqDepends, TaskiqScheduler
from taskiq.cli.scheduler.run import SchedulerLoop
from taskiq_postgresql import PostgresqlBroker
from taskiq_postgresql.scheduler_source import PostgresqlSchedulerSource

from media_manager.automation.dependencies import get_automation_service
from media_manager.automation.service import AutomationService
from media_manager.episode_scanner.dependencies import (
    get_episode_scan_runner,
    get_episode_scan_service,
)
from media_manager.episode_scanner.schemas import EpisodeScanRunId
from media_manager.episode_scanner.service import (
    EpisodeScanRunner,
    EpisodeScanService,
)
from media_manager.movies.dependencies import get_movie_service
from media_manager.movies.service import MovieService
from media_manager.recommendations.dependencies import get_recommendation_service
from media_manager.recommendations.service import RecommendationService
from media_manager.tv.dependencies import get_tv_service
from media_manager.tv.service import TvService


def _build_db_connection_string_for_taskiq() -> str:
    from media_manager.config import MediaManagerConfig

    db_config = MediaManagerConfig().database
    user = quote(db_config.user, safe="")
    password = quote(db_config.password, safe="")
    dbname = quote(db_config.dbname, safe="")
    host = quote(str(db_config.host), safe="")
    port = quote(str(db_config.port), safe="")
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


broker = PostgresqlBroker(
    dsn=_build_db_connection_string_for_taskiq,
    driver="psycopg",
    run_migrations=True,
)

# Register FastAPI app with the broker so worker processes can resolve FastAPI
# dependencies. Using a string reference avoids circular imports.
taskiq_fastapi.init(broker, "media_manager.main:app")

log = logging.getLogger(__name__)


@broker.task
async def import_all_movie_torrents_task(
    movie_service: MovieService = TaskiqDepends(get_movie_service),
) -> None:
    log.info("Importing all Movie torrents")
    await movie_service.import_all_torrents()


@broker.task
async def import_all_show_torrents_task(
    tv_service: TvService = TaskiqDepends(get_tv_service),
) -> None:
    log.info("Importing all Show torrents")
    await tv_service.import_all_torrents()


@broker.task
async def update_all_movies_metadata_task(
    movie_service: MovieService = TaskiqDepends(get_movie_service),
) -> None:
    await movie_service.update_all_metadata()


@broker.task
async def update_all_non_ended_shows_metadata_task(
    tv_service: TvService = TaskiqDepends(get_tv_service),
) -> None:
    await tv_service.update_all_non_ended_shows_metadata()


@broker.task
async def run_download_automation_task(
    automation_service: AutomationService = TaskiqDepends(get_automation_service),
) -> None:
    """Search for and enqueue releases that are due for automatic download."""
    result = await automation_service.run_automation_cycle()
    log.info(
        "Automatic download cycle finished: queued=%d claimed=%d succeeded=%d "
        "retrying=%d failed=%d skipped=%d",
        result.queued,
        result.claimed,
        result.succeeded,
        result.retrying,
        result.failed,
        result.skipped,
    )


@broker.task
async def run_episode_scan_task(
    run_id: str,
    scan_runner: EpisodeScanRunner = TaskiqDepends(get_episode_scan_runner),
) -> None:
    """Check every TV show for new episodes and send them to the download client."""
    await scan_runner.execute(EpisodeScanRunId(UUID(run_id)))


@broker.task
async def schedule_episode_scan_task(
    scan_service: EpisodeScanService = TaskiqDepends(get_episode_scan_service),
) -> None:
    """Start the hourly episode scan when automatic scanning is on and due.

    This check is cheap, so it runs often; the expensive scan itself runs in
    its own task with the indexer and download-client dependencies.
    """
    run = await scan_service.start_scheduled_scan_if_due()
    if run is None:
        return
    try:
        await run_episode_scan_task.kiq(run_id=str(run.id))
    except Exception as error:
        log.exception("Could not queue scheduled episode scan %s", run.id)
        await scan_service.mark_start_failed(run.id, error)


@broker.task
async def refresh_personal_recommendations_task(
    recommendation_service: RecommendationService = TaskiqDepends(
        get_recommendation_service
    ),
) -> None:
    """Refresh Plex/Tautulli-backed recommendations that have become due."""
    results = await recommendation_service.refresh_due_users()
    if results:
        log.info("Refreshed personal recommendations for %d user(s)", len(results))


# Maps each task to its cron schedule so PostgresqlSchedulerSource can seed
# the taskiq_schedulers table on first startup.
_STARTUP_SCHEDULES: dict[str, list[dict[str, str]]] = {
    import_all_movie_torrents_task.task_name: [{"cron": "*/2 * * * *"}],
    import_all_show_torrents_task.task_name: [{"cron": "*/2 * * * *"}],
    update_all_movies_metadata_task.task_name: [{"cron": "0 0 * * 1"}],
    update_all_non_ended_shows_metadata_task.task_name: [{"cron": "0 */6 * * *"}],
    run_download_automation_task.task_name: [{"cron": "*/5 * * * *"}],
    # The due-check runs every five minutes; the scan itself runs once per
    # configured interval (hourly by default). Keep in sync with
    # media_manager.episode_scanner.service.SCHEDULER_TICK_MINUTES.
    schedule_episode_scan_task.task_name: [{"cron": "*/5 * * * *"}],
    refresh_personal_recommendations_task.task_name: [{"cron": "*/15 * * * *"}],
}


def build_scheduler_loop() -> SchedulerLoop:
    source = PostgresqlSchedulerSource(
        dsn=_build_db_connection_string_for_taskiq,
        driver="psycopg",
        broker=broker,
        run_migrations=True,
        startup_schedule=_STARTUP_SCHEDULES,
    )
    scheduler = TaskiqScheduler(broker=broker, sources=[source])
    return SchedulerLoop(scheduler)
