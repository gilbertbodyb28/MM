from typing import Self

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings


class TraktConfig(BaseSettings):
    enabled: bool = False
    client_id: SecretStr | None = None
    client_secret: SecretStr | None = None
    redirect_uri: AnyHttpUrl = AnyHttpUrl(
        "http://localhost:8000/api/v1/trakt/callback"
    )
    frontend_return_url: AnyHttpUrl = AnyHttpUrl(
        "http://localhost:8000/web/dashboard/trakt"
    )
    api_url: AnyHttpUrl = AnyHttpUrl("https://api.trakt.tv")
    authorize_url: AnyHttpUrl = AnyHttpUrl("https://trakt.tv/oauth/authorize")
    token_url: AnyHttpUrl = AnyHttpUrl("https://api.trakt.tv/oauth/token")
    verify_ssl: bool = True
    request_timeout_seconds: float = Field(default=30, gt=0, le=300)

    @model_validator(mode="after")
    def require_credentials_when_enabled(self) -> Self:
        if not self.enabled:
            return self
        if self.client_id is None or not self.client_id.get_secret_value().strip():
            msg = "Trakt requires a client ID when enabled"
            raise ValueError(msg)
        if (
            self.client_secret is None
            or not self.client_secret.get_secret_value().strip()
        ):
            msg = "Trakt requires a client secret when enabled"
            raise ValueError(msg)
        return self


class SeerrConfig(BaseSettings):
    enabled: bool = False
    url: AnyHttpUrl = AnyHttpUrl("http://localhost:5055")
    api_key: SecretStr | None = None
    verify_ssl: bool = True
    request_timeout_seconds: float = Field(default=30, gt=0, le=300)

    @model_validator(mode="after")
    def require_key_when_enabled(self) -> Self:
        if self.enabled and (
            self.api_key is None or not self.api_key.get_secret_value().strip()
        ):
            msg = "Seerr requires an API key when enabled"
            raise ValueError(msg)
        return self


class IntegrationsConfig(BaseSettings):
    trakt: TraktConfig = TraktConfig()
    seerr: SeerrConfig = SeerrConfig()
