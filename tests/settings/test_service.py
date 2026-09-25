# ruff: noqa: S101

from media_manager.settings.schemas import (
    IntegrationSettingsUpdate,
    OllamaSettingsUpdate,
    PlexSettingsUpdate,
    ProwlarrSettingsUpdate,
    QbittorrentSettingsUpdate,
    RecommendationSettingsUpdate,
    SeerrSettingsUpdate,
    TautulliSettingsUpdate,
    TmdbSettingsUpdate,
    TraktSettingsUpdate,
    TvdbSettingsUpdate,
)
from media_manager.settings.service import IntegrationSettingsService


def _request() -> IntegrationSettingsUpdate:
    return IntegrationSettingsUpdate(
        prowlarr=ProwlarrSettingsUpdate(
            enabled=True,
            url="http://prowlarr:9696",
            api_key=None,
        ),
        qbittorrent=QbittorrentSettingsUpdate(
            enabled=True,
            host="qbittorrent",
            port=8080,
            username="admin",
            password=None,
        ),
        tmdb=TmdbSettingsUpdate(
            tmdb_relay_url="https://relay.example/tmdb",
            api_key=None,
            access_token=None,
        ),
        tvdb=TvdbSettingsUpdate(
            tvdb_relay_url="https://relay.example/tvdb",
            api_key=None,
            pin=None,
        ),
        recommendations=RecommendationSettingsUpdate(
            enabled=False,
            tautulli=TautulliSettingsUpdate(
                enabled=False,
                url="http://tautulli:8181",
            ),
            plex=PlexSettingsUpdate(
                enabled=False,
                url="http://plex:32400",
            ),
            ollama=OllamaSettingsUpdate(
                enabled=False,
                url="http://ollama:11434",
                model="llama3.2",
            ),
        ),
        trakt=TraktSettingsUpdate(
            enabled=False,
            redirect_uri="http://localhost:8000/api/v1/trakt/callback",
            frontend_return_url="http://localhost:5173/dashboard/trakt",
        ),
        seerr=SeerrSettingsUpdate(
            enabled=False,
            url="http://seerr:5055",
        ),
    )


def test_overlay_omits_blank_secrets_so_existing_values_are_preserved() -> None:
    overlay = IntegrationSettingsService._to_overlay(_request())

    assert "api_key" not in overlay["indexers"]["prowlarr"]
    assert "password" not in overlay["torrents"]["qbittorrent"]
    assert "api_key" not in overlay["metadata"]["tmdb"]
    assert "access_token" not in overlay["metadata"]["tmdb"]
    assert "token" not in overlay["recommendations"]["plex"]
    assert "client_id" not in overlay["integrations"]["trakt"]
    assert "client_secret" not in overlay["integrations"]["trakt"]
    assert "api_key" not in overlay["integrations"]["seerr"]


def test_overlay_can_explicitly_clear_secrets() -> None:
    request = _request()
    request.prowlarr.clear_api_key = True
    request.qbittorrent.clear_password = True
    request.tmdb.clear_access_token = True
    request.tvdb.clear_pin = True
    request.recommendations.plex.clear_token = True
    assert request.trakt is not None
    assert request.seerr is not None
    request.trakt.clear_client_id = True
    request.trakt.clear_client_secret = True
    request.seerr.clear_api_key = True
    overlay = IntegrationSettingsService._to_overlay(request)

    assert overlay["indexers"]["prowlarr"]["api_key"] == ""
    assert overlay["torrents"]["qbittorrent"]["password"] == ""
    assert overlay["metadata"]["tmdb"]["access_token"] is None
    assert overlay["metadata"]["tvdb"]["pin"] is None
    assert overlay["recommendations"]["plex"]["token"] is None
    assert overlay["integrations"]["trakt"]["client_id"] is None
    assert overlay["integrations"]["trakt"]["client_secret"] is None
    assert overlay["integrations"]["seerr"]["api_key"] is None


def test_overlay_preserves_integrations_for_legacy_clients() -> None:
    request = _request()
    request.trakt = None
    request.seerr = None

    overlay = IntegrationSettingsService._to_overlay(request)

    assert "integrations" not in overlay
