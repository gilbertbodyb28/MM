from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EpisodeScannerConfig(BaseSettings):
    """Tuning for the hourly episode scanner.

    Whether the scanner runs is a UI setting stored in the database; these
    values only shape how a scan behaves.
    """

    model_config = SettingsConfigDict(
        env_prefix="MEDIAMANAGER_EPISODE_SCANNER__",
        case_sensitive=False,
    )

    interval_minutes: int = Field(default=60, ge=5, le=1440)
    # Only episodes that aired within this window count as "new". Older gaps
    # are left to the explicit continuous-download automation so enabling the
    # scanner never bulk-downloads a show's back catalogue.
    lookback_days: int = Field(default=14, ge=1, le=365)
    include_specials: bool = False
    history_days: int = Field(default=30, ge=1, le=365)
    # A running scan renews its lease every ``heartbeat_seconds``. One that has
    # not done so for ``lease_timeout_seconds`` is treated as interrupted (for
    # example after a container restart) so a new scan can start.
    heartbeat_seconds: int = Field(default=30, ge=5, le=600)
    lease_timeout_seconds: int = Field(default=300, ge=60, le=86_400)
