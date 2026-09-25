from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AutomationConfig(BaseSettings):
    """Configuration for automatic release searches and downloads."""

    model_config = SettingsConfigDict(
        env_prefix="MEDIAMANAGER_AUTOMATION__",
        case_sensitive=False,
    )

    enabled: bool = False
    # Movie automation is intentionally opt-in. Enabling the TV monitor must not
    # unexpectedly enqueue every movie already present in the library.
    auto_download_movies: bool = False
    auto_download_shows: bool = True
    continuous_download_enabled: bool = True
    include_specials: bool = False

    process_batch_size: int = Field(default=5, ge=1, le=100)
    max_releases_per_show_cycle: int = Field(default=50, ge=1, le=500)
    max_attempts: int = Field(default=6, ge=1, le=100)
    base_backoff_seconds: int = Field(default=300, ge=1)
    max_backoff_seconds: int = Field(default=21600, ge=1)
    exhausted_retry_seconds: int = Field(default=86400, ge=1)
    lease_timeout_seconds: int = Field(default=1800, ge=60)
