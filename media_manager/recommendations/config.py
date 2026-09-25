from typing import Literal, Self
from uuid import UUID

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings


class RecommendationUserMapping(BaseSettings):
    """Maps a Media Manager user to identities from local history providers."""

    user_id: UUID
    tautulli_user_id: str | None = None
    plex_account_id: str | None = None
    plex_username: str | None = None
    enabled: bool = True

    @field_validator("tautulli_user_id", "plex_account_id", "plex_username")
    @classmethod
    def normalize_external_identity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def require_external_identity(self) -> Self:
        if not any((self.tautulli_user_id, self.plex_account_id, self.plex_username)):
            msg = "A recommendation user mapping requires an external identity"
            raise ValueError(msg)
        return self


class TautulliRecommendationConfig(BaseSettings):
    enabled: bool = False
    url: AnyHttpUrl = AnyHttpUrl("http://localhost:8181")
    api_key: SecretStr | None = None
    verify_ssl: bool = True
    request_timeout_seconds: float = Field(default=20.0, gt=0, le=300)

    @model_validator(mode="after")
    def require_api_key_when_enabled(self) -> Self:
        if self.enabled and (
            self.api_key is None or not self.api_key.get_secret_value().strip()
        ):
            msg = "Tautulli requires an API key when enabled"
            raise ValueError(msg)
        return self


class PlexRecommendationConfig(BaseSettings):
    enabled: bool = False
    url: AnyHttpUrl = AnyHttpUrl("http://localhost:32400")
    token: SecretStr | None = None
    verify_ssl: bool = True
    request_timeout_seconds: float = Field(default=20.0, gt=0, le=300)
    webhook_enabled: bool = False
    webhook_secret: SecretStr | None = None
    server_uuid: str | None = None

    @field_validator("server_uuid")
    @classmethod
    def normalize_server_uuid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().casefold()
        return normalized or None

    @model_validator(mode="after")
    def require_credentials_for_enabled_features(self) -> Self:
        if self.enabled and (
            self.token is None or not self.token.get_secret_value().strip()
        ):
            msg = "Plex history requires a token when enabled"
            raise ValueError(msg)
        if self.webhook_enabled and (
            self.webhook_secret is None
            or not self.webhook_secret.get_secret_value().strip()
        ):
            msg = "Plex webhooks require a webhook secret when enabled"
            raise ValueError(msg)
        return self


class OllamaRecommendationConfig(BaseSettings):
    enabled: bool = False
    url: AnyHttpUrl = AnyHttpUrl("http://localhost:11434")
    model: str = Field(default="llama3.2", min_length=1, max_length=200)
    api_key: SecretStr | None = None
    verify_ssl: bool = True
    request_timeout_seconds: float = Field(default=120.0, gt=0, le=900)
    keep_alive: str = Field(default="5m", min_length=1, max_length=32)
    max_response_bytes: int = Field(default=1_000_000, ge=1_024, le=10_000_000)

    @field_validator("model")
    @classmethod
    def normalize_model_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            msg = "Ollama model name cannot be blank"
            raise ValueError(msg)
        return normalized


class RecommendationConfig(BaseSettings):
    """Typed configuration owned by the recommendations domain."""

    enabled: bool = False
    history_provider: Literal["auto", "tautulli", "plex"] = "auto"
    refresh_interval_minutes: int = Field(default=360, ge=15, le=43_200)
    refresh_lease_timeout_seconds: int = Field(default=3_600, ge=60, le=86_400)
    history_page_size: int = Field(default=100, ge=1, le=1_000)
    max_history_items_per_sync: int = Field(default=1_000, ge=1, le=25_000)
    prompt_history_items: int = Field(default=150, ge=1, le=1_000)
    metadata_enrichment_limit: int = Field(default=25, ge=0, le=250)
    recommendation_count: int = Field(default=20, ge=1, le=50)
    section_count: int = Field(default=20, ge=20, le=40)
    section_item_count: int = Field(default=25, ge=25, le=50)
    section_candidate_budget: int = Field(default=500, ge=25, le=500)
    section_fetch_concurrency: int = Field(default=4, ge=1, le=8)
    plex_library_cache_minutes: int = Field(default=15, ge=1, le=240)
    minimum_history_items: int = Field(default=3, ge=1, le=100)
    recommendation_ttl_hours: int = Field(default=168, ge=1, le=8_760)
    generate_on_webhook: bool = False
    max_webhook_payload_bytes: int = Field(
        default=1_000_000,
        ge=1_024,
        le=10_000_000,
    )
    tautulli: TautulliRecommendationConfig = TautulliRecommendationConfig()
    plex: PlexRecommendationConfig = PlexRecommendationConfig()
    ollama: OllamaRecommendationConfig = OllamaRecommendationConfig()
    users: list[RecommendationUserMapping] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_configuration(self) -> Self:
        user_ids = [mapping.user_id for mapping in self.users]
        if len(user_ids) != len(set(user_ids)):
            msg = "Each Media Manager user can only have one recommendation mapping"
            raise ValueError(msg)

        if not self.enabled:
            return self

        if not self.ollama.enabled:
            msg = "Ollama must be enabled when recommendations are enabled"
            raise ValueError(msg)
        if self.history_provider == "tautulli" and not self.tautulli.enabled:
            msg = "The selected Tautulli history provider is not enabled"
            raise ValueError(msg)
        if self.history_provider == "plex" and not self.plex.enabled:
            msg = "The selected Plex history provider is not enabled"
            raise ValueError(msg)
        if (
            self.history_provider == "auto"
            and not self.tautulli.enabled
            and not self.plex.enabled
            and not self.plex.webhook_enabled
        ):
            msg = "At least one history source must be enabled"
            raise ValueError(msg)
        return self

    def mapping_for_user(self, user_id: UUID) -> RecommendationUserMapping | None:
        return next(
            (mapping for mapping in self.users if mapping.user_id == user_id),
            None,
        )
