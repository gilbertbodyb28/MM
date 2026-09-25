# ruff: noqa: S101

import logging
from types import SimpleNamespace
from typing import cast

import pytest
import requests
from _pytest.logging import LogCaptureFixture

from media_manager.indexer.utils import (
    follow_redirects_to_final_torrent_url,
    sanitize_url_for_logging,
)


def test_sanitize_url_for_logging_removes_credentials_query_and_fragment() -> None:
    url = (
        "https://account:password@example.invalid:8443/download/file.torrent"
        "?apikey=test-secret#private-fragment"
    )

    assert (
        sanitize_url_for_logging(url)
        == "https://example.invalid:8443/download/file.torrent"
    )


def test_redirect_failure_never_logs_secret_urls(
    caplog: LogCaptureFixture,
) -> None:
    sensitive_value = "test-indexer-api-key"
    initial_url = f"https://indexer.invalid/start?apikey={sensitive_value}#private"
    redirect_url = (
        f"https://indexer.invalid/download/item.torrent?apikey={sensitive_value}"
    )

    class Session:
        calls = 0

        def get(
            self,
            url: str,
            *,
            allow_redirects: bool,
            timeout: float,
        ) -> SimpleNamespace:
            assert allow_redirects is False
            assert timeout == 10
            self.calls += 1
            if self.calls == 1:
                assert url == initial_url
                return SimpleNamespace(
                    status_code=302,
                    headers={"Location": redirect_url},
                )
            error_message = f"Connection failed for {url}"
            raise requests.ConnectionError(error_message)

    caplog.set_level(logging.DEBUG)
    try:
        follow_redirects_to_final_torrent_url(
            initial_url,
            cast(requests.Session, Session()),
        )
    except RuntimeError:
        # Simulate a caller logging the sanitized wrapper exception.
        logging.getLogger("test.downstream").exception("Redirect resolution failed")
    else:
        pytest.fail("The simulated request failure should be wrapped")

    assert sensitive_value not in caplog.text
    assert "private-fragment" not in caplog.text
    assert "https://indexer.invalid/download/item.torrent" in caplog.text
    assert "ConnectionError" in caplog.text
