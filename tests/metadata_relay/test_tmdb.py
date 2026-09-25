# ruff: noqa: S101

import os
from datetime import date

import pytest
from fastapi import HTTPException

from metadata_relay.app.tmdb import (
    DiscoverSort,
    MediaType,
    _discover_params,
    _discover_sort,
    require_tmdb_api_key,
)


def test_movie_discover_parameters_use_official_tmdb_names() -> None:
    params = _discover_params(
        MediaType.MOVIE,
        language="sv-SE",
        page=3,
        region="SE",
        year=2025,
        year_from=2020,
        year_to=2025,
        release_date_from=None,
        genres="12,878",
        rating_min=6.5,
        rating_max=9.5,
        sort_by=DiscoverSort.RELEASE_DATE_DESC,
        include_adult=False,
    )

    assert params == {
        "language": "sv-SE",
        "page": 3,
        "sort_by": "primary_release_date.desc",
        "include_adult": False,
        "include_video": False,
        "region": "SE",
        "primary_release_year": 2025,
        "primary_release_date.gte": "2020-01-01",
        "primary_release_date.lte": "2025-12-31",
        "with_genres": "12,878",
        "vote_average.gte": 6.5,
        "vote_average.lte": 9.5,
    }


def test_tv_sort_aliases_map_to_tmdb_fields() -> None:
    assert (
        _discover_sort(MediaType.TV, DiscoverSort.RELEASE_DATE_ASC)
        == "first_air_date.asc"
    )
    assert _discover_sort(MediaType.TV, DiscoverSort.TITLE_DESC) == "name.desc"


def test_tv_discover_year_range_uses_first_air_date() -> None:
    params = _discover_params(
        MediaType.TV,
        language="en",
        page=1,
        region=None,
        year=None,
        year_from=2010,
        year_to=2020,
        release_date_from=None,
        genres=None,
        rating_min=None,
        rating_max=None,
        sort_by=DiscoverSort.POPULARITY_DESC,
        include_adult=False,
    )

    assert params["first_air_date.gte"] == "2010-01-01"
    assert params["first_air_date.lte"] == "2020-12-31"


def test_upcoming_boundary_is_combined_with_year_filter() -> None:
    params = _discover_params(
        MediaType.MOVIE,
        language="en",
        page=1,
        region=None,
        year=None,
        year_from=2026,
        year_to=None,
        release_date_from=date(2026, 8, 14),
        genres=None,
        rating_min=None,
        rating_max=None,
        sort_by=DiscoverSort.RELEASE_DATE_ASC,
        include_adult=False,
    )

    assert params["primary_release_date.gte"] == "2026-08-14"


def test_missing_api_key_returns_service_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TMDB_API_KEY", raising=False)

    with pytest.raises(HTTPException) as exception_info:
        require_tmdb_api_key()

    assert exception_info.value.status_code == 503


def test_api_key_is_loaded_for_each_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "test-key")
    require_tmdb_api_key()
    assert os.environ["TMDB_API_KEY"] == "test-key"
