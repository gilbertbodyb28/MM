from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator


def _endpoint(value: str) -> str:
    from urllib.parse import urlsplit

    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        msg = "Enter a complete http:// or https:// URL"
        raise ValueError(msg)
    if parsed.username or parsed.password:
        msg = "Credentials must not be embedded in a URL"
        raise ValueError(msg)
    return normalized


def _optional_secret(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class ProwlarrSettingsUpdate(BaseModel):
    enabled: bool
    url: str
    api_key: str | None = Field(default=None, max_length=500)
    clear_api_key: bool = False
    timeout_seconds: int = Field(default=60, ge=1, le=300)
    max_results: int = Field(default=1000, ge=1, le=1000)

    _validate_url = field_validator("url")(_endpoint)
    _normalize_api_key = field_validator("api_key")(_optional_secret)


class ProwlarrSettingsRead(BaseModel):
    enabled: bool
    url: str
    api_key_configured: bool
    timeout_seconds: int
    max_results: int


class QbittorrentSettingsUpdate(BaseModel):
    enabled: bool
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str = Field(default="", max_length=320)
    password: str | None = Field(default=None, max_length=500)
    clear_password: bool = False
    category_name: str = Field(default="MediaManager", min_length=1, max_length=200)
    category_save_path: str = Field(
        default="/data/torrents", min_length=1, max_length=1000
    )

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        from urllib.parse import urlsplit

        normalized = value.strip().rstrip("/")
        parsed = urlsplit(
            normalized if "://" in normalized else f"http://{normalized}"
        )
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            msg = "Enter a hostname, IP address, or HTTP URL"
            raise ValueError(msg)
        if parsed.username or parsed.password or parsed.path not in {"", "/"}:
            msg = "qBittorrent host must not include credentials or a path"
            raise ValueError(msg)
        return normalized

    _normalize_password = field_validator("password")(_optional_secret)


class QbittorrentSettingsRead(BaseModel):
    enabled: bool
    host: str
    port: int
    username: str
    password_configured: bool
    category_name: str
    category_save_path: str


class TmdbSettingsUpdate(BaseModel):
    api_key: str | None = Field(default=None, max_length=500)
    access_token: str | None = Field(default=None, max_length=2000)
    clear_api_key: bool = False
    clear_access_token: bool = False
    tmdb_relay_url: str
    default_language: str = Field(default="en", min_length=2, max_length=16)
    primary_languages: list[str] = Field(default_factory=list, max_length=20)

    _validate_url = field_validator("tmdb_relay_url")(_endpoint)
    _normalize_api_key = field_validator("api_key")(_optional_secret)
    _normalize_token = field_validator("access_token")(_optional_secret)

    @field_validator("default_language")
    @classmethod
    def normalize_default_language(cls, value: str) -> str:
        return value.strip()

    @field_validator("primary_languages")
    @classmethod
    def normalize_languages(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))


class TmdbSettingsRead(BaseModel):
    api_key_configured: bool
    access_token_configured: bool
    direct_configured: bool
    tmdb_relay_url: str
    default_language: str
    primary_languages: list[str]


class TvdbSettingsUpdate(BaseModel):
    api_key: str | None = Field(default=None, max_length=500)
    pin: str | None = Field(default=None, max_length=500)
    clear_api_key: bool = False
    clear_pin: bool = False
    tvdb_relay_url: str

    _validate_url = field_validator("tvdb_relay_url")(_endpoint)
    _normalize_api_key = field_validator("api_key")(_optional_secret)
    _normalize_pin = field_validator("pin")(_optional_secret)


class TvdbSettingsRead(BaseModel):
    api_key_configured: bool
    pin_configured: bool
    direct_configured: bool
    tvdb_relay_url: str


class TautulliSettingsUpdate(BaseModel):
    enabled: bool
    url: str
    api_key: str | None = Field(default=None, max_length=500)
    clear_api_key: bool = False
    verify_ssl: bool = True
    request_timeout_seconds: float = Field(default=20, gt=0, le=300)

    _validate_url = field_validator("url")(_endpoint)
    _normalize_api_key = field_validator("api_key")(_optional_secret)


class TautulliSettingsRead(BaseModel):
    enabled: bool
    url: str
    api_key_configured: bool
    verify_ssl: bool
    request_timeout_seconds: float


class PlexSettingsUpdate(BaseModel):
    enabled: bool
    url: str
    token: str | None = Field(default=None, max_length=2000)
    clear_token: bool = False
    verify_ssl: bool = True
    request_timeout_seconds: float = Field(default=20, gt=0, le=300)
    webhook_enabled: bool = False
    webhook_secret: str | None = Field(default=None, max_length=500)
    clear_webhook_secret: bool = False
    server_uuid: str | None = Field(default=None, max_length=200)

    _validate_url = field_validator("url")(_endpoint)
    _normalize_token = field_validator("token")(_optional_secret)
    _normalize_webhook = field_validator("webhook_secret")(_optional_secret)

    @field_validator("server_uuid")
    @classmethod
    def normalize_server_uuid(cls, value: str | None) -> str | None:
        return _optional_secret(value)


class PlexSettingsRead(BaseModel):
    enabled: bool
    url: str
    token_configured: bool
    verify_ssl: bool
    request_timeout_seconds: float
    webhook_enabled: bool
    webhook_secret_configured: bool
    server_uuid: str | None


class OllamaSettingsUpdate(BaseModel):
    enabled: bool
    url: str
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, max_length=2000)
    clear_api_key: bool = False
    verify_ssl: bool = True
    request_timeout_seconds: float = Field(default=120, gt=0, le=900)
    keep_alive: str = Field(default="5m", min_length=1, max_length=32)

    _validate_url = field_validator("url")(_endpoint)
    _normalize_api_key = field_validator("api_key")(_optional_secret)


class OllamaSettingsRead(BaseModel):
    enabled: bool
    url: str
    model: str
    api_key_configured: bool
    verify_ssl: bool
    request_timeout_seconds: float
    keep_alive: str


class RecommendationSettingsUpdate(BaseModel):
    enabled: bool
    history_provider: Literal["auto", "tautulli", "plex"] = "auto"
    refresh_interval_minutes: int = Field(default=360, ge=15, le=43_200)
    recommendation_count: int = Field(default=20, ge=1, le=50)
    minimum_history_items: int = Field(default=3, ge=1, le=100)
    tautulli: TautulliSettingsUpdate
    plex: PlexSettingsUpdate
    ollama: OllamaSettingsUpdate


class RecommendationSettingsRead(BaseModel):
    enabled: bool
    history_provider: Literal["auto", "tautulli", "plex"]
    refresh_interval_minutes: int
    recommendation_count: int
    minimum_history_items: int
    tautulli: TautulliSettingsRead
    plex: PlexSettingsRead
    ollama: OllamaSettingsRead


class TraktSettingsUpdate(BaseModel):
    enabled: bool
    client_id: str | None = Field(default=None, max_length=1_000)
    client_secret: str | None = Field(default=None, max_length=2_000)
    clear_client_id: bool = False
    clear_client_secret: bool = False
    redirect_uri: str
    frontend_return_url: str
    verify_ssl: bool = True
    request_timeout_seconds: float = Field(default=30, gt=0, le=300)

    _validate_redirect = field_validator("redirect_uri")(_endpoint)
    _validate_return = field_validator("frontend_return_url")(_endpoint)
    _normalize_client_id = field_validator("client_id")(_optional_secret)
    _normalize_client_secret = field_validator("client_secret")(_optional_secret)


class TraktSettingsRead(BaseModel):
    enabled: bool
    client_id_configured: bool
    client_secret_configured: bool
    redirect_uri: str
    frontend_return_url: str
    verify_ssl: bool
    request_timeout_seconds: float


class SeerrSettingsUpdate(BaseModel):
    enabled: bool
    url: str
    api_key: str | None = Field(default=None, max_length=2_000)
    clear_api_key: bool = False
    verify_ssl: bool = True
    request_timeout_seconds: float = Field(default=30, gt=0, le=300)

    _validate_url = field_validator("url")(_endpoint)
    _normalize_api_key = field_validator("api_key")(_optional_secret)


class SeerrSettingsRead(BaseModel):
    enabled: bool
    url: str
    api_key_configured: bool
    verify_ssl: bool
    request_timeout_seconds: float


class IntegrationSettingsUpdate(BaseModel):
    prowlarr: ProwlarrSettingsUpdate
    qbittorrent: QbittorrentSettingsUpdate
    tmdb: TmdbSettingsUpdate
    tvdb: TvdbSettingsUpdate
    recommendations: RecommendationSettingsUpdate
    # Optional for backwards compatibility with clients that predate these
    # integrations. Missing sections preserve the current server configuration.
    trakt: TraktSettingsUpdate | None = None
    seerr: SeerrSettingsUpdate | None = None


class IntegrationSettingsRead(BaseModel):
    prowlarr: ProwlarrSettingsRead
    qbittorrent: QbittorrentSettingsRead
    tmdb: TmdbSettingsRead
    tvdb: TvdbSettingsRead
    recommendations: RecommendationSettingsRead
    trakt: TraktSettingsRead
    seerr: SeerrSettingsRead


class ConnectionTestResult(BaseModel):
    service: Literal[
        "prowlarr",
        "qbittorrent",
        "tmdb",
        "tvdb",
        "tautulli",
        "plex",
        "ollama",
        "trakt",
        "seerr",
    ]
    ok: bool
    message: str


class RecommendationMappingUpdate(BaseModel):
    tautulli_user_id: str | None = Field(default=None, max_length=128)
    plex_account_id: str | None = Field(default=None, max_length=128)
    plex_username: str | None = Field(default=None, max_length=320)
    enabled: bool = True

    @field_validator("tautulli_user_id", "plex_account_id", "plex_username")
    @classmethod
    def normalize_identity(cls, value: str | None) -> str | None:
        return _optional_secret(value)

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if self.enabled and not any(
            (self.tautulli_user_id, self.plex_account_id, self.plex_username)
        ):
            msg = "Enter at least one Plex or Tautulli identity"
            raise ValueError(msg)
        return self


class RecommendationMappingRead(BaseModel):
    tautulli_user_id: str | None = None
    plex_account_id: str | None = None
    plex_username: str | None = None
    enabled: bool = False
    configured: bool = False
