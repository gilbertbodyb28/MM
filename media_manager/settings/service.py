import asyncio
import logging
from copy import deepcopy
from typing import Any, Literal

import httpx
import qbittorrentapi
import tvdb_v4_official
from pydantic import SecretStr, ValidationError

from media_manager.config import MediaManagerConfig
from media_manager.metadataProvider.tmdb_transport import TmdbTransport
from media_manager.settings.schemas import (
    ConnectionTestResult,
    IntegrationSettingsRead,
    IntegrationSettingsUpdate,
    OllamaSettingsRead,
    PlexSettingsRead,
    ProwlarrSettingsRead,
    QbittorrentSettingsRead,
    RecommendationSettingsRead,
    SeerrSettingsRead,
    TautulliSettingsRead,
    TmdbSettingsRead,
    TraktSettingsRead,
    TvdbSettingsRead,
)
from media_manager.settings.store import RuntimeSettingsStore

log = logging.getLogger(__name__)

MISSING_CREDENTIAL = "missing credential"
UNHEALTHY_RESPONSE = "unhealthy response"
AUTHENTICATION_FAILED = "authentication failed"

ServiceName = Literal[
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


def _secret_value(value: SecretStr | str | None) -> str | None:
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class IntegrationSettingsService:
    def __init__(self, store: RuntimeSettingsStore | None = None) -> None:
        self.store = store or RuntimeSettingsStore()

    def get(self) -> IntegrationSettingsRead:
        config = MediaManagerConfig()
        prowlarr = config.indexers.prowlarr
        qbittorrent = config.torrents.qbittorrent
        tmdb = config.metadata.tmdb
        tvdb = config.metadata.tvdb
        recommendations = config.recommendations
        trakt = config.integrations.trakt
        seerr = config.integrations.seerr

        return IntegrationSettingsRead(
            prowlarr=ProwlarrSettingsRead(
                enabled=prowlarr.enabled,
                url=prowlarr.url,
                api_key_configured=bool(prowlarr.api_key.strip()),
                timeout_seconds=prowlarr.timeout_seconds,
                max_results=prowlarr.max_results,
            ),
            qbittorrent=QbittorrentSettingsRead(
                enabled=qbittorrent.enabled,
                host=qbittorrent.host,
                port=qbittorrent.port,
                username=qbittorrent.username,
                password_configured=bool(qbittorrent.password),
                category_name=qbittorrent.category_name,
                category_save_path=qbittorrent.category_save_path,
            ),
            tmdb=TmdbSettingsRead(
                api_key_configured=bool(_secret_value(tmdb.api_key)),
                access_token_configured=bool(_secret_value(tmdb.access_token)),
                direct_configured=bool(
                    _secret_value(tmdb.api_key) or _secret_value(tmdb.access_token)
                ),
                tmdb_relay_url=tmdb.tmdb_relay_url,
                default_language=tmdb.default_language,
                primary_languages=tmdb.primary_languages,
            ),
            tvdb=TvdbSettingsRead(
                api_key_configured=bool(_secret_value(tvdb.api_key)),
                pin_configured=bool(_secret_value(tvdb.pin)),
                direct_configured=bool(_secret_value(tvdb.api_key)),
                tvdb_relay_url=tvdb.tvdb_relay_url,
            ),
            recommendations=RecommendationSettingsRead(
                enabled=recommendations.enabled,
                history_provider=recommendations.history_provider,
                refresh_interval_minutes=recommendations.refresh_interval_minutes,
                recommendation_count=recommendations.recommendation_count,
                minimum_history_items=recommendations.minimum_history_items,
                tautulli=TautulliSettingsRead(
                    enabled=recommendations.tautulli.enabled,
                    url=str(recommendations.tautulli.url).rstrip("/"),
                    api_key_configured=bool(
                        _secret_value(recommendations.tautulli.api_key)
                    ),
                    verify_ssl=recommendations.tautulli.verify_ssl,
                    request_timeout_seconds=(
                        recommendations.tautulli.request_timeout_seconds
                    ),
                ),
                plex=PlexSettingsRead(
                    enabled=recommendations.plex.enabled,
                    url=str(recommendations.plex.url).rstrip("/"),
                    token_configured=bool(_secret_value(recommendations.plex.token)),
                    verify_ssl=recommendations.plex.verify_ssl,
                    request_timeout_seconds=(
                        recommendations.plex.request_timeout_seconds
                    ),
                    webhook_enabled=recommendations.plex.webhook_enabled,
                    webhook_secret_configured=bool(
                        _secret_value(recommendations.plex.webhook_secret)
                    ),
                    server_uuid=recommendations.plex.server_uuid,
                ),
                ollama=OllamaSettingsRead(
                    enabled=recommendations.ollama.enabled,
                    url=str(recommendations.ollama.url).rstrip("/"),
                    model=recommendations.ollama.model,
                    api_key_configured=bool(
                        _secret_value(recommendations.ollama.api_key)
                    ),
                    verify_ssl=recommendations.ollama.verify_ssl,
                    request_timeout_seconds=(
                        recommendations.ollama.request_timeout_seconds
                    ),
                    keep_alive=recommendations.ollama.keep_alive,
                ),
            ),
            trakt=TraktSettingsRead(
                enabled=trakt.enabled,
                client_id_configured=bool(_secret_value(trakt.client_id)),
                client_secret_configured=bool(_secret_value(trakt.client_secret)),
                redirect_uri=str(trakt.redirect_uri),
                frontend_return_url=str(trakt.frontend_return_url),
                verify_ssl=trakt.verify_ssl,
                request_timeout_seconds=trakt.request_timeout_seconds,
            ),
            seerr=SeerrSettingsRead(
                enabled=seerr.enabled,
                url=str(seerr.url).rstrip("/"),
                api_key_configured=bool(_secret_value(seerr.api_key)),
                verify_ssl=seerr.verify_ssl,
                request_timeout_seconds=seerr.request_timeout_seconds,
            ),
        )

    def update(self, request: IntegrationSettingsUpdate) -> IntegrationSettingsRead:
        patch = self._to_overlay(request)
        current_overlay = self.store.read()
        candidate_overlay = _deep_merge(current_overlay, patch)

        # Validate the complete effective configuration before any bytes are written.
        effective = MediaManagerConfig().model_dump()
        try:
            MediaManagerConfig.model_validate(_deep_merge(effective, patch))
        except ValidationError:
            # Pydantic validation messages can include submitted input.  Keep the API
            # error generic so credentials are never reflected to clients or logs.
            msg = "The integration settings are incomplete or invalid"
            raise ValueError(msg) from None

        self.store.write(candidate_overlay)
        return self.get()

    @staticmethod
    def _to_overlay(request: IntegrationSettingsUpdate) -> dict[str, Any]:
        raw = request.model_dump(exclude_none=True)

        prowlarr = raw["prowlarr"]
        if prowlarr.pop("clear_api_key", False):
            prowlarr["api_key"] = ""

        qbittorrent = raw["qbittorrent"]
        if qbittorrent.pop("clear_password", False):
            qbittorrent["password"] = ""

        tmdb = raw["tmdb"]
        if tmdb.pop("clear_api_key", False):
            tmdb["api_key"] = None
        if tmdb.pop("clear_access_token", False):
            tmdb["access_token"] = None

        tvdb = raw["tvdb"]
        if tvdb.pop("clear_api_key", False):
            tvdb["api_key"] = None
        if tvdb.pop("clear_pin", False):
            tvdb["pin"] = None

        recommendations = raw["recommendations"]
        tautulli = recommendations["tautulli"]
        if tautulli.pop("clear_api_key", False):
            tautulli["api_key"] = None
        plex = recommendations["plex"]
        if plex.pop("clear_token", False):
            plex["token"] = None
        if plex.pop("clear_webhook_secret", False):
            plex["webhook_secret"] = None
        ollama = recommendations["ollama"]
        if ollama.pop("clear_api_key", False):
            ollama["api_key"] = None

        integrations: dict[str, Any] = {}
        if trakt := raw.get("trakt"):
            if trakt.pop("clear_client_id", False):
                trakt["client_id"] = None
            if trakt.pop("clear_client_secret", False):
                trakt["client_secret"] = None
            integrations["trakt"] = trakt

        if seerr := raw.get("seerr"):
            if seerr.pop("clear_api_key", False):
                seerr["api_key"] = None
            integrations["seerr"] = seerr

        overlay: dict[str, Any] = {
            "indexers": {"prowlarr": prowlarr},
            "torrents": {"qbittorrent": qbittorrent},
            "metadata": {"tmdb": tmdb, "tvdb": tvdb},
            "recommendations": recommendations,
        }
        if integrations:
            overlay["integrations"] = integrations
        return overlay

    async def test(self, service: ServiceName) -> ConnectionTestResult:
        tests = {
            "prowlarr": self._test_prowlarr,
            "qbittorrent": self._test_qbittorrent,
            "tmdb": self._test_tmdb,
            "tvdb": self._test_tvdb,
            "tautulli": self._test_tautulli,
            "plex": self._test_plex,
            "ollama": self._test_ollama,
            "trakt": self._test_trakt,
            "seerr": self._test_seerr,
        }
        try:
            await tests[service]()
        except Exception as error:
            log.warning(
                "Integration connection test failed for %s (%s)",
                service,
                type(error).__name__,
            )
            return ConnectionTestResult(
                service=service,
                ok=False,
                message="Connection failed. Check the address and credentials.",
            )
        return ConnectionTestResult(
            service=service,
            ok=True,
            message="Connection successful.",
        )

    async def _test_prowlarr(self) -> None:
        config = MediaManagerConfig().indexers.prowlarr
        if not config.api_key.strip():
            raise ValueError(MISSING_CREDENTIAL)
        async with httpx.AsyncClient(follow_redirects=False, timeout=15) as client:
            response = await client.get(
                f"{config.url.rstrip('/')}/api/v1/system/status",
                headers={"X-Api-Key": config.api_key},
            )
            if response.is_error:
                raise RuntimeError(UNHEALTHY_RESPONSE)

    async def _test_qbittorrent(self) -> None:
        config = MediaManagerConfig().torrents.qbittorrent

        def check() -> None:
            client = qbittorrentapi.Client(
                host=config.host,
                port=config.port,
                username=config.username,
                password=config.password,
            )
            try:
                client.auth_log_in()
                client.app_version()
            finally:
                try:
                    client.auth_log_out()
                except Exception as error:
                    log.debug(
                        "qBittorrent logout after connection test failed (%s)",
                        type(error).__name__,
                    )

        await asyncio.to_thread(check)

    async def _test_tmdb(self) -> None:
        async with httpx.AsyncClient(follow_redirects=False, timeout=15) as client:
            transport = TmdbTransport(client=client)
            path = "/configuration" if transport.direct else "/movies/popular"
            await transport.get(path, {"page": 1}, request_timeout=15)

    async def _test_tvdb(self) -> None:
        config = MediaManagerConfig().metadata.tvdb
        api_key = _secret_value(config.api_key)
        if api_key:
            pin = _secret_value(config.pin)

            def check() -> None:
                client = tvdb_v4_official.TVDB(api_key, pin=pin)
                client.search("Breaking Bad")

            await asyncio.to_thread(check)
            return
        async with httpx.AsyncClient(follow_redirects=False, timeout=15) as client:
            response = await client.get(
                f"{config.tvdb_relay_url.rstrip('/')}/tv/search",
                params={"query": "Breaking Bad"},
            )
            if response.is_error:
                raise RuntimeError(UNHEALTHY_RESPONSE)

    async def _test_tautulli(self) -> None:
        config = MediaManagerConfig().recommendations.tautulli
        api_key = _secret_value(config.api_key)
        if not api_key:
            raise ValueError(MISSING_CREDENTIAL)
        async with httpx.AsyncClient(
            verify=config.verify_ssl,
            follow_redirects=False,
            timeout=min(config.request_timeout_seconds, 30),
        ) as client:
            response = await client.get(
                f"{str(config.url).rstrip('/')}/api/v2",
                params={"apikey": api_key, "cmd": "get_server_info"},
            )
            if response.is_error:
                raise RuntimeError(UNHEALTHY_RESPONSE)
            payload = response.json()
            if payload.get("response", {}).get("result") != "success":
                raise RuntimeError(AUTHENTICATION_FAILED)

    async def _test_plex(self) -> None:
        config = MediaManagerConfig().recommendations.plex
        token = _secret_value(config.token)
        if not token:
            raise ValueError(MISSING_CREDENTIAL)
        async with httpx.AsyncClient(
            verify=config.verify_ssl,
            follow_redirects=False,
            timeout=min(config.request_timeout_seconds, 30),
        ) as client:
            response = await client.get(
                f"{str(config.url).rstrip('/')}/identity",
                headers={"X-Plex-Token": token},
            )
            if response.is_error:
                raise RuntimeError(UNHEALTHY_RESPONSE)

    async def _test_ollama(self) -> None:
        config = MediaManagerConfig().recommendations.ollama
        api_key = _secret_value(config.api_key)
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        async with httpx.AsyncClient(
            verify=config.verify_ssl,
            follow_redirects=False,
            timeout=min(config.request_timeout_seconds, 30),
        ) as client:
            response = await client.get(
                f"{str(config.url).rstrip('/')}/api/tags",
                headers=headers,
            )
            if response.is_error:
                raise RuntimeError(UNHEALTHY_RESPONSE)

    async def _test_trakt(self) -> None:
        config = MediaManagerConfig().integrations.trakt
        client_id = _secret_value(config.client_id)
        client_secret = _secret_value(config.client_secret)
        if not client_id or not client_secret:
            raise ValueError(MISSING_CREDENTIAL)
        async with httpx.AsyncClient(
            verify=config.verify_ssl,
            follow_redirects=False,
            timeout=min(config.request_timeout_seconds, 30),
        ) as client:
            response = await client.get(
                f"{str(config.api_url).rstrip('/')}/movies/trending",
                params={"limit": 1},
                headers={
                    "Content-Type": "application/json",
                    "trakt-api-key": client_id,
                    "trakt-api-version": "2",
                },
            )
            if response.is_error:
                raise RuntimeError(UNHEALTHY_RESPONSE)

    async def _test_seerr(self) -> None:
        config = MediaManagerConfig().integrations.seerr
        api_key = _secret_value(config.api_key)
        if not api_key:
            raise ValueError(MISSING_CREDENTIAL)
        async with httpx.AsyncClient(
            verify=config.verify_ssl,
            follow_redirects=False,
            timeout=min(config.request_timeout_seconds, 30),
        ) as client:
            response = await client.get(
                f"{str(config.url).rstrip('/')}/api/v1/status",
                headers={"X-Api-Key": api_key},
            )
            if response.is_error:
                raise RuntimeError(UNHEALTHY_RESPONSE)
