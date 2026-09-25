# ruff: noqa: S101

import logging
from typing import NoReturn

import pytest
import requests
from _pytest.logging import LogCaptureFixture

from media_manager.indexer.schemas import IndexerQueryResult
from media_manager.torrent import utils as torrent_utils


def make_result(download_url: str) -> IndexerQueryResult:
    return IndexerQueryResult(
        title="Example.Release.1080p",
        download_url=download_url,
        seeders=10,
        flags=[],
        size=1_000_000,
        usenet=False,
        age=0,
        indexer="test",
    )


def test_torrent_download_request_failure_does_not_log_secret(
    monkeypatch: pytest.MonkeyPatch,
    caplog: LogCaptureFixture,
) -> None:
    sensitive_value = "test-indexer-api-key"
    download_url = (
        "https://indexer.invalid/download/item.torrent"
        f"?apikey={sensitive_value}#private"
    )

    def fail_request(url: str, *, timeout: int) -> NoReturn:
        assert timeout == 30
        error_message = f"Connection failed for {url}"
        raise requests.ConnectionError(error_message)

    monkeypatch.setattr(torrent_utils.requests, "get", fail_request)
    caplog.set_level(logging.DEBUG, logger="media_manager.torrent.utils")

    with pytest.raises(RuntimeError, match="Failed to download torrent file"):
        torrent_utils.get_torrent_hash(make_result(download_url))

    assert sensitive_value not in caplog.text
    assert "private" not in caplog.text
    assert "https://indexer.invalid/download/item.torrent" in caplog.text
    assert "ConnectionError" in caplog.text


def test_invalid_schema_fallback_does_not_log_secret_exception(
    monkeypatch: pytest.MonkeyPatch,
    caplog: LogCaptureFixture,
) -> None:
    sensitive_value = "test-indexer-api-key"
    download_url = f"indexer://download/item?apikey={sensitive_value}#private"
    expected_hash = "0123456789abcdef0123456789abcdef01234567"

    def reject_schema(url: str, *, timeout: int) -> NoReturn:
        assert timeout == 30
        error_message = f"Unsupported URL {url}"
        raise requests.exceptions.InvalidSchema(error_message)

    monkeypatch.setattr(torrent_utils.requests, "get", reject_schema)
    monkeypatch.setattr(
        torrent_utils,
        "follow_redirects_to_final_torrent_url",
        lambda **_kwargs: f"magnet:?xt=urn:btih:{expected_hash}",
    )
    caplog.set_level(logging.DEBUG, logger="media_manager.torrent.utils")

    torrent_hash = torrent_utils.get_torrent_hash(make_result(download_url))

    assert torrent_hash == expected_hash
    assert sensitive_value not in caplog.text
    assert "private" not in caplog.text
    assert "indexer://download/item" in caplog.text


def test_invalid_schema_is_not_retained_when_fallback_fails(
    monkeypatch: pytest.MonkeyPatch,
    caplog: LogCaptureFixture,
) -> None:
    sensitive_value = "test-indexer-api-key"
    download_url = f"indexer://download/item?apikey={sensitive_value}#private"

    def reject_schema(url: str, *, timeout: int) -> NoReturn:
        assert timeout == 30
        error_message = f"Unsupported URL {url}"
        raise requests.exceptions.InvalidSchema(error_message)

    def fail_fallback(**_kwargs: object) -> NoReturn:
        error_message = "Redirect resolution failed"
        raise RuntimeError(error_message)

    monkeypatch.setattr(torrent_utils.requests, "get", reject_schema)
    monkeypatch.setattr(
        torrent_utils,
        "follow_redirects_to_final_torrent_url",
        fail_fallback,
    )
    caplog.set_level(logging.DEBUG)

    try:
        torrent_utils.get_torrent_hash(make_result(download_url))
    except RuntimeError:
        logging.getLogger("test.downstream").exception("Torrent fallback failed")
    else:
        pytest.fail("The simulated fallback failure should propagate")

    assert sensitive_value not in caplog.text
    assert "private" not in caplog.text
