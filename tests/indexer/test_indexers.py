# ruff: noqa: S101

import logging
from types import SimpleNamespace

from _pytest.logging import LogCaptureFixture

from media_manager.indexer.indexers.jackett import Jackett
from media_manager.indexer.indexers.prowlarr import IndexerInfo, Prowlarr
from media_manager.indexer.schemas import IndexerQueryResult


def make_result(title: str) -> IndexerQueryResult:
    return IndexerQueryResult(
        title=title,
        download_url=f"https://indexer.invalid/{title}",
        seeders=10,
        flags=[],
        size=1_000_000,
        usenet=False,
        age=0,
        indexer="test",
    )


def make_indexer_info() -> IndexerInfo:
    return IndexerInfo(
        id=7,
        name="Test Indexer",
        supports_tv_search=True,
        supports_tv_search_tmdb=False,
        supports_tv_search_imdb=False,
        supports_tv_search_tvdb=False,
        supports_tv_search_season=True,
        supports_tv_search_episode=True,
        supports_movie_search=True,
        supports_movie_search_tmdb=False,
        supports_movie_search_imdb=False,
        supports_movie_search_tvdb=False,
    )


def test_prowlarr_requests_and_enforces_configured_result_limit() -> None:
    prowlarr = object.__new__(Prowlarr)
    prowlarr.config = SimpleNamespace(max_results=2)
    captured_parameters: dict[str, str | int | None] = {}

    def call_api(
        *, path: str, parameters: dict[str, str | int | None]
    ) -> SimpleNamespace:
        assert path == "/indexer/7/newznab"
        captured_parameters.update(parameters)
        return SimpleNamespace(content=b"response")

    prowlarr._call_prowlarr_api = call_api  # type: ignore[method-assign]

    def process_search_result(xml: bytes) -> list[IndexerQueryResult]:
        assert xml == b"response"
        return [make_result("One"), make_result("Two"), make_result("Three")]

    prowlarr.process_search_result = (  # type: ignore[method-assign]
        process_search_result
    )
    original_parameters = {"q": "Example", "t": "movie"}

    results = prowlarr._newznab_search(make_indexer_info(), original_parameters)

    assert [result.title for result in results] == ["One", "Two"]
    assert captured_parameters["limit"] == 2
    assert original_parameters == {"q": "Example", "t": "movie"}


def test_prowlarr_continues_when_one_indexer_is_rate_limited(
    caplog: LogCaptureFixture,
) -> None:
    prowlarr = object.__new__(Prowlarr)
    limited = make_indexer_info()
    healthy = make_indexer_info()
    limited.name = "Rate Limited"
    healthy.id = 8
    healthy.name = "Healthy"
    prowlarr._get_tv_indexers = lambda: [limited, healthy]  # type: ignore[method-assign]

    def search_indexer(
        indexer: IndexerInfo,
        parameters: dict[str, str | int | None],
    ) -> list[IndexerQueryResult]:
        assert parameters["q"] == "Example"
        if indexer is limited:
            message = "429 apiKey=super-secret"
            raise RuntimeError(message)
        return [make_result("Found elsewhere")]

    prowlarr._newznab_search = search_indexer  # type: ignore[method-assign]
    caplog.set_level(logging.WARNING, logger="media_manager.indexer.indexers.prowlarr")

    results = prowlarr.search("Example", is_tv=True)

    assert [result.title for result in results] == ["Found elsewhere"]
    assert "Rate Limited failed (RuntimeError)" in caplog.text
    assert "super-secret" not in caplog.text
    assert "Traceback" not in caplog.text


def test_jackett_caps_results_without_logging_api_key(
    caplog: LogCaptureFixture,
) -> None:
    jackett = object.__new__(Jackett)
    jackett.url = "http://jackett.invalid"
    jackett.api_key = "super-secret-api-key"
    jackett.timeout_seconds = 5
    jackett.max_results = 2
    jackett._Jackett__get_optimal_query_parameters = (  # type: ignore[method-assign]
        lambda indexer, session, params: {  # noqa: ARG005
            "apikey": jackett.api_key,
            "t": "movie",
        }
    )
    jackett.process_search_result = lambda _content: [  # type: ignore[method-assign]
        make_result("One"),
        make_result("Two"),
        make_result("Three"),
    ]

    class Session:
        def get(
            self,
            url: str,
            *,
            timeout: int,
            params: dict[str, str | int],
        ) -> SimpleNamespace:
            assert timeout == jackett.timeout_seconds
            assert params["apikey"] == jackett.api_key
            return SimpleNamespace(
                status_code=200,
                content=b"response",
                url=f"{url}?apikey={jackett.api_key}&t=movie",
            )

    caplog.set_level(logging.DEBUG, logger="media_manager.indexer.indexers.jackett")
    results = jackett.get_torrents_by_indexer(
        "test-indexer",
        {"q": "Example", "t": "movie"},
        Session(),  # type: ignore[arg-type]
    )

    assert [result.title for result in results] == ["One", "Two"]
    assert "super-secret-api-key" not in caplog.text
    assert "/api/v2.0/indexers/test-indexer/results/torznab/api" in caplog.text
