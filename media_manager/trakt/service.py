import asyncio
import base64
import hashlib
import hmac
import json
import logging
import secrets
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlencode
from uuid import UUID

import httpx

from media_manager.config import MediaManagerConfig
from media_manager.integrations.config import TraktConfig
from media_manager.metadataProvider.tmdb_transport import (
    TmdbTransport,
    TmdbTransportError,
)
from media_manager.trakt.repository import TraktRepository
from media_manager.trakt.schemas import (
    TraktAuthorizeResponse,
    TraktConnectionData,
    TraktIds,
    TraktItemCollection,
    TraktMediaItem,
    TraktStatus,
)

log = logging.getLogger(__name__)

TraktSource = Literal["watchlist", "collection", "history", "lists"]
TraktMediaFilter = Literal["all", "movie", "show"]


class TraktConfigurationError(RuntimeError):
    """The administrator has not completed Trakt configuration."""


class TraktAuthenticationError(RuntimeError):
    """The current user's Trakt connection is missing or invalid."""


class TraktProviderError(RuntimeError):
    """A sanitized upstream Trakt failure."""


class TraktService:
    def __init__(
        self,
        repository: TraktRepository,
        config: TraktConfig | None = None,
    ) -> None:
        app_config = MediaManagerConfig()
        self.repository = repository
        self.config = config or app_config.integrations.trakt
        self._state_secret = app_config.auth.token_secret.encode()

    async def status(self, user_id: UUID) -> TraktStatus:
        connection = await self.repository.get(user_id)
        return TraktStatus(
            configured=self._configured(),
            connected=connection is not None,
            username=connection.account_username if connection else None,
            slug=connection.account_slug if connection else None,
            expires_at=connection.expires_at if connection else None,
        )

    def authorization_url(self, user_id: UUID) -> TraktAuthorizeResponse:
        self._require_configured()
        client_id, _client_secret = self._credentials()
        state = self._sign_state(user_id)
        query = urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": str(self.config.redirect_uri),
                "state": state,
            }
        )
        return TraktAuthorizeResponse(
            authorization_url=f"{str(self.config.authorize_url).rstrip('/')}?{query}"
        )

    async def connect(self, user_id: UUID, *, code: str, state: str) -> None:
        self._require_configured()
        if self._verify_state(state) != user_id:
            msg = "Trakt authorization state is invalid or expired"
            raise TraktAuthenticationError(msg)
        client_id, client_secret = self._credentials()
        token_payload = await self._token_request(
            {
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": str(self.config.redirect_uri),
                "grant_type": "authorization_code",
            }
        )
        connection = self._connection_from_token(user_id, token_payload)
        account = await self._account(connection)
        user = account.get("user", {}) if isinstance(account, Mapping) else {}
        ids = user.get("ids", {}) if isinstance(user, Mapping) else {}
        connection.account_username = self._text(
            user.get("username") if isinstance(user, Mapping) else None
        )
        connection.account_slug = self._text(
            ids.get("slug") if isinstance(ids, Mapping) else None
        )
        connection.trakt_user_id = self._text(
            ids.get("trakt") if isinstance(ids, Mapping) else None
        )
        await self.repository.upsert(connection)

    async def disconnect(self, user_id: UUID) -> None:
        await self.repository.delete(user_id)

    async def list_items(
        self,
        user_id: UUID,
        *,
        source: TraktSource,
        media_type: TraktMediaFilter = "all",
    ) -> TraktItemCollection:
        connection = await self._active_connection(user_id)
        async with httpx.AsyncClient(
            verify=self.config.verify_ssl,
            timeout=self.config.request_timeout_seconds,
            follow_redirects=False,
        ) as client:
            payloads: list[tuple[str, object]] = []
            selected_types = (
                ("movies", "shows")
                if media_type == "all"
                else (("movies",) if media_type == "movie" else ("shows",))
            )
            if source == "lists":
                payloads = await self._list_payloads(
                    client,
                    connection,
                    selected_types,
                )
            else:
                for resource_type in selected_types:
                    rows = await self._get(
                        client,
                        connection,
                        f"/sync/{source}/{resource_type}",
                        {"extended": "full", "limit": 1_000, "page": 1},
                    )
                    payloads.append((source, rows))

            items = self._normalize_items(payloads)
            await self._enrich_posters(client, items)
            return TraktItemCollection(source=source, items=items, total=len(items))

    async def _list_payloads(
        self,
        client: httpx.AsyncClient,
        connection: TraktConnectionData,
        resource_types: tuple[str, ...],
    ) -> list[tuple[str, object]]:
        raw_lists = await self._get(
            client,
            connection,
            "/users/me/lists",
            {"extended": "full", "limit": 100, "page": 1},
        )
        if not isinstance(raw_lists, list):
            return []
        semaphore = asyncio.Semaphore(4)

        async def fetch_list(raw_list: object) -> list[tuple[str, object]]:
            if not isinstance(raw_list, Mapping):
                return []
            ids = raw_list.get("ids", {})
            list_id = ids.get("trakt") if isinstance(ids, Mapping) else None
            if list_id is None:
                return []
            list_name = self._text(raw_list.get("name")) or f"List {list_id}"
            async with semaphore:
                results = []
                for resource_type in resource_types:
                    rows = await self._get(
                        client,
                        connection,
                        f"/users/me/lists/{list_id}/items/{resource_type}",
                        {"extended": "full", "limit": 1_000, "page": 1},
                    )
                    results.append((f"list:{list_name}", rows))
                return results

        nested = await asyncio.gather(*(fetch_list(item) for item in raw_lists))
        return [entry for group in nested for entry in group]

    async def _enrich_posters(
        self,
        client: httpx.AsyncClient,
        items: list[TraktMediaItem],
    ) -> None:
        transport = TmdbTransport(client=client)
        semaphore = asyncio.Semaphore(8)

        async def enrich(item: TraktMediaItem) -> None:
            if item.ids.tmdb is None:
                return
            resource = "movies" if item.media_type == "movie" else "tv/shows"
            try:
                async with semaphore:
                    payload = await transport.get(
                        f"/{resource}/{item.ids.tmdb}",
                        request_timeout=min(self.config.request_timeout_seconds, 60),
                    )
            except TmdbTransportError:
                return
            poster = self._text(payload.get("poster_path"))
            if poster:
                item.poster_path = poster

        await asyncio.gather(*(enrich(item) for item in items))

    async def _active_connection(self, user_id: UUID) -> TraktConnectionData:
        self._require_configured()
        connection = await self.repository.get(user_id)
        if connection is None:
            msg = "Connect a Trakt account before loading Trakt data"
            raise TraktAuthenticationError(msg)
        if connection.expires_at > datetime.now(UTC) + timedelta(minutes=2):
            return connection
        if not connection.refresh_token:
            msg = "The Trakt session expired. Connect the account again."
            raise TraktAuthenticationError(msg)
        client_id, client_secret = self._credentials()
        payload = await self._token_request(
            {
                "refresh_token": connection.refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": str(self.config.redirect_uri),
                "grant_type": "refresh_token",
            }
        )
        refreshed = self._connection_from_token(user_id, payload)
        refreshed.account_username = connection.account_username
        refreshed.account_slug = connection.account_slug
        refreshed.trakt_user_id = connection.trakt_user_id
        await self.repository.upsert(refreshed)
        return refreshed

    async def _token_request(self, body: Mapping[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                verify=self.config.verify_ssl,
                timeout=self.config.request_timeout_seconds,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    str(self.config.token_url),
                    json=dict(body),
                    headers={"Content-Type": "application/json"},
                )
        except httpx.HTTPError as error:
            msg = "Trakt could not be reached"
            raise TraktProviderError(msg) from error
        if response.status_code in {400, 401, 403}:
            msg = "Trakt rejected the authorization request"
            raise TraktAuthenticationError(msg)
        if response.status_code == 429:
            msg = "Trakt is rate limited. Try again shortly."
            raise TraktProviderError(msg)
        if response.is_error:
            msg = "Trakt authorization is temporarily unavailable"
            raise TraktProviderError(msg)
        try:
            payload = response.json()
        except ValueError as error:
            msg = "Trakt returned an invalid authorization response"
            raise TraktProviderError(msg) from error
        if not isinstance(payload, dict):
            msg = "Trakt returned an invalid authorization response"
            raise TraktProviderError(msg)
        return payload

    async def _account(self, connection: TraktConnectionData) -> dict[str, Any]:
        async with httpx.AsyncClient(
            verify=self.config.verify_ssl,
            timeout=self.config.request_timeout_seconds,
            follow_redirects=False,
        ) as client:
            payload = await self._get(client, connection, "/users/settings")
        if not isinstance(payload, dict):
            msg = "Trakt returned invalid account information"
            raise TraktProviderError(msg)
        return payload

    async def _get(
        self,
        client: httpx.AsyncClient,
        connection: TraktConnectionData,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> object:
        client_id, _client_secret = self._credentials()
        try:
            response = await client.get(
                f"{str(self.config.api_url).rstrip('/')}/{path.lstrip('/')}",
                params=params,
                headers={
                    "Authorization": f"Bearer {connection.access_token}",
                    "Content-Type": "application/json",
                    "trakt-api-key": client_id,
                    "trakt-api-version": "2",
                },
            )
        except httpx.HTTPError as error:
            msg = "Trakt could not be reached"
            raise TraktProviderError(msg) from error
        if response.status_code in {401, 403}:
            msg = "The Trakt session is no longer authorized"
            raise TraktAuthenticationError(msg)
        if response.status_code == 429:
            msg = "Trakt is rate limited. Try again shortly."
            raise TraktProviderError(msg)
        if response.is_error:
            msg = "Trakt data is temporarily unavailable"
            raise TraktProviderError(msg)
        try:
            return response.json()
        except ValueError as error:
            msg = "Trakt returned invalid data"
            raise TraktProviderError(msg) from error

    @classmethod
    def _normalize_items(
        cls,
        payloads: list[tuple[str, object]],
    ) -> list[TraktMediaItem]:
        items: dict[str, TraktMediaItem] = {}
        for source_label, payload in payloads:
            if not isinstance(payload, list):
                continue
            for row in payload:
                if not isinstance(row, Mapping):
                    continue
                media_type: Literal["movie", "show"] | None = None
                media: object = row.get("movie")
                if isinstance(media, Mapping):
                    media_type = "movie"
                else:
                    media = row.get("show")
                    if isinstance(media, Mapping):
                        media_type = "show"
                if media_type is None or not isinstance(media, Mapping):
                    continue
                title = cls._text(media.get("title"))
                raw_ids = media.get("ids", {})
                if title is None or not isinstance(raw_ids, Mapping):
                    continue
                ids = TraktIds(
                    trakt=cls._int(raw_ids.get("trakt")),
                    slug=cls._text(raw_ids.get("slug")),
                    imdb=cls._text(raw_ids.get("imdb")),
                    tmdb=cls._int(raw_ids.get("tmdb")),
                    tvdb=cls._int(raw_ids.get("tvdb")),
                )
                identity = ids.tmdb or ids.trakt
                if identity is None:
                    continue
                key = f"{media_type}:{identity}"
                existing = items.get(key)
                if existing is not None:
                    if source_label not in existing.sources:
                        existing.sources.append(source_label)
                    continue
                items[key] = TraktMediaItem(
                    key=key,
                    media_type=media_type,
                    title=title,
                    year=cls._int(media.get("year")),
                    ids=ids,
                    sources=[source_label],
                )
        return sorted(
            items.values(),
            key=lambda item: (item.title.casefold(), item.year or 0),
        )

    def _connection_from_token(
        self,
        user_id: UUID,
        payload: Mapping[str, Any],
    ) -> TraktConnectionData:
        access_token = self._text(payload.get("access_token"))
        if access_token is None:
            msg = "Trakt did not return an access token"
            raise TraktProviderError(msg)
        created_at = self._int(payload.get("created_at"))
        expires_in = self._int(payload.get("expires_in")) or 7_776_000
        issued_at = (
            datetime.fromtimestamp(created_at, tz=UTC)
            if created_at is not None
            else datetime.now(UTC)
        )
        return TraktConnectionData(
            user_id=user_id,
            access_token=access_token,
            refresh_token=self._text(payload.get("refresh_token")),
            token_type=self._text(payload.get("token_type")) or "bearer",
            scope=self._text(payload.get("scope")),
            expires_at=issued_at + timedelta(seconds=expires_in),
        )

    def _sign_state(self, user_id: UUID) -> str:
        payload = json.dumps(
            {
                "user_id": str(user_id),
                "expires": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
                "nonce": secrets.token_urlsafe(18),
            },
            separators=(",", ":"),
        ).encode()
        encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        signature = hmac.new(
            self._state_secret,
            encoded.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"{encoded}.{signature}"

    def _verify_state(self, state: str) -> UUID | None:
        try:
            encoded, signature = state.split(".", maxsplit=1)
            expected = hmac.new(
                self._state_secret,
                encoded.encode(),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return None
            padded = encoded + "=" * (-len(encoded) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded))
            if int(payload["expires"]) < int(datetime.now(UTC).timestamp()):
                return None
            return UUID(str(payload["user_id"]))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _configured(self) -> bool:
        return bool(
            self.config.enabled
            and self.config.client_id
            and self.config.client_id.get_secret_value().strip()
            and self.config.client_secret
            and self.config.client_secret.get_secret_value().strip()
        )

    def _require_configured(self) -> None:
        if not self._configured():
            msg = "Trakt is not configured. Add its OAuth credentials in Settings."
            raise TraktConfigurationError(msg)

    def _credentials(self) -> tuple[str, str]:
        self._require_configured()
        assert self.config.client_id is not None  # noqa: S101
        assert self.config.client_secret is not None  # noqa: S101
        return (
            self.config.client_id.get_secret_value(),
            self.config.client_secret.get_secret_value(),
        )

    @staticmethod
    def _text(value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @staticmethod
    def _int(value: object) -> int | None:
        try:
            parsed = int(str(value))
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None
