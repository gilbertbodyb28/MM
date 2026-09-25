from collections.abc import Mapping
from typing import Any

import httpx

from media_manager.config import MediaManagerConfig
from media_manager.integrations.config import SeerrConfig
from media_manager.recommendations.clients import PlexClient
from media_manager.recommendations.exceptions import RecommendationProviderError
from media_manager.seerr.schemas import (
    SeerrConfiguredStatus,
    SeerrMediaStatus,
    SeerrRequestCreate,
    SeerrRequestResult,
    SeerrState,
)


class SeerrConfigurationError(RuntimeError):
    """Seerr credentials are not configured."""


class SeerrProviderError(RuntimeError):
    """A sanitized upstream Seerr failure."""


class SeerrService:
    def __init__(self, config: SeerrConfig | None = None) -> None:
        app_config = MediaManagerConfig()
        self.config = config or app_config.integrations.seerr
        self._plex_config = app_config.recommendations.plex

    def configured(self) -> SeerrConfiguredStatus:
        return SeerrConfiguredStatus(configured=self._configured())

    async def media_status(
        self,
        media_type: str,
        tmdb_id: int,
    ) -> SeerrMediaStatus:
        resource = "movie" if media_type == "movie" else "tv"
        payload = await self._request("GET", f"/{resource}/{tmdb_id}")
        return self._normalize_status(media_type, tmdb_id, payload)

    async def create_request(
        self,
        request: SeerrRequestCreate,
    ) -> SeerrRequestResult:
        if await self._exists_in_plex(request.media_type, request.tmdb_id):
            return SeerrRequestResult(
                media_type=request.media_type,
                tmdb_id=request.tmdb_id,
                status="available",
                message="This title already exists in Plex, so no Seerr request was sent.",
            )
        body: dict[str, Any] = {
            "mediaType": request.media_type,
            "mediaId": request.tmdb_id,
        }
        if request.media_type == "tv":
            body["seasons"] = request.seasons or "all"
        try:
            payload = await self._request("POST", "/request", json_body=body)
        except SeerrProviderError as error:
            if getattr(error, "status_code", None) != 409:
                raise
            current = await self.media_status(request.media_type, request.tmdb_id)
            return SeerrRequestResult(
                **current.model_dump(),
                message="This title already has a Seerr request.",
            )

        normalized = self._normalize_status(
            request.media_type,
            request.tmdb_id,
            payload,
        )
        if normalized.status in {"not_requested", "unknown"}:
            normalized.status = "requested"
        return SeerrRequestResult(
            **normalized.model_dump(),
            message="Request sent to Seerr.",
        )

    async def _exists_in_plex(self, media_type: str, tmdb_id: int) -> bool:
        if not self._plex_config.enabled or self._plex_config.token is None:
            return False
        try:
            inventory = await PlexClient(self._plex_config).get_library_inventory()
        except RecommendationProviderError as error:
            msg = "Plex could not be checked, so the Seerr request was not sent"
            raise SeerrProviderError(msg) from error
        expected_type = "movie" if media_type == "movie" else "show"
        return any(
            item.media_type == expected_type
            and item.external_ids.get("tmdb") == str(tmdb_id)
            for item in inventory
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_configured()
        assert self.config.api_key is not None  # noqa: S101
        try:
            async with httpx.AsyncClient(
                verify=self.config.verify_ssl,
                follow_redirects=False,
                timeout=self.config.request_timeout_seconds,
            ) as client:
                response = await client.request(
                    method,
                    f"{str(self.config.url).rstrip('/')}/api/v1/{path.lstrip('/')}",
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "X-Api-Key": self.config.api_key.get_secret_value(),
                    },
                    json=dict(json_body) if json_body is not None else None,
                )
        except httpx.HTTPError as error:
            msg = "Seerr could not be reached"
            raise SeerrProviderError(msg) from error
        if response.status_code in {401, 403}:
            msg = "Seerr rejected the configured API key"
            raise SeerrProviderError(msg)
        if response.status_code == 429:
            msg = "Seerr is rate limited. Try again shortly."
            raise SeerrProviderError(msg)
        if response.is_error:
            msg = "Seerr could not complete the request"
            provider_error = SeerrProviderError(msg)
            provider_error.status_code = response.status_code  # type: ignore[attr-defined]
            raise provider_error
        try:
            payload = response.json()
        except ValueError as error:
            msg = "Seerr returned invalid data"
            raise SeerrProviderError(msg) from error
        if not isinstance(payload, dict):
            msg = "Seerr returned invalid data"
            raise SeerrProviderError(msg)
        return payload

    @classmethod
    def _normalize_status(
        cls,
        media_type: str,
        tmdb_id: int,
        payload: Mapping[str, Any],
    ) -> SeerrMediaStatus:
        media_info = payload.get("mediaInfo") or payload.get("media") or {}
        if not isinstance(media_info, Mapping):
            media_info = {}
        media_status = cls._int(media_info.get("status"))

        request_payload: object = payload
        requests = payload.get("requests")
        if isinstance(requests, list) and requests:
            request_payload = requests[0]
        if not isinstance(request_payload, Mapping):
            request_payload = {}
        request_status = cls._int(request_payload.get("status"))
        request_id = cls._int(request_payload.get("id"))
        state = cls._state(media_status, request_status, request_id)
        return SeerrMediaStatus(
            media_type="movie" if media_type == "movie" else "tv",
            tmdb_id=tmdb_id,
            status=state,
            request_id=request_id,
            media_status=media_status,
            request_status=request_status,
        )

    @staticmethod
    def _state(
        media_status: int | None,
        request_status: int | None,
        request_id: int | None,
    ) -> SeerrState:
        media_states: dict[int, SeerrState] = {
            2: "pending",
            3: "processing",
            4: "partially_available",
            5: "available",
        }
        if media_status in media_states:
            return media_states[media_status]
        request_states: dict[int, SeerrState] = {
            1: "pending",
            2: "approved",
            3: "declined",
        }
        if request_status in request_states:
            return request_states[request_status]
        return "requested" if request_id is not None else "not_requested"

    def _configured(self) -> bool:
        return bool(
            self.config.enabled
            and self.config.api_key
            and self.config.api_key.get_secret_value().strip()
        )

    def _require_configured(self) -> None:
        if not self._configured():
            msg = "Seerr is not configured. Add its URL and API key in Settings."
            raise SeerrConfigurationError(msg)

    @staticmethod
    def _int(value: object) -> int | None:
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return None
