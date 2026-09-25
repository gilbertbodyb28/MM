# ruff: noqa: S101

from datetime import UTC, datetime

from media_manager.recommendations.catalog import TmdbRecommendationCatalog
from media_manager.recommendations.schemas import (
    RecommendationCandidate,
    RecommendationSource,
)


def test_candidate_normalizes_movie_metadata_without_overview_content() -> None:
    candidate = TmdbRecommendationCatalog._candidate(
        {
            "id": 329865,
            "title": " Arrival ",
            "release_date": "2016-11-11",
            "poster_path": "/poster.jpg",
            "genre_ids": [878, 18, "invalid"],
            "original_language": "en",
            "vote_average": 7.6,
            "popularity": 92.4,
            "overview": "This is deliberately not copied into poster-card data.",
        },
        "movie",
    )

    assert candidate is not None
    assert candidate.external_id == 329865
    assert candidate.name == "Arrival"
    assert candidate.year == 2016
    assert candidate.genre_ids == [878, 18]
    assert candidate.poster_path == "/poster.jpg"


def test_candidate_rejects_missing_identity_or_title() -> None:
    assert TmdbRecommendationCatalog._candidate({"title": "No ID"}, "movie") is None
    assert TmdbRecommendationCatalog._candidate({"id": 1}, "show") is None
    assert TmdbRecommendationCatalog._candidate("invalid", "movie") is None


def test_grounded_score_prefers_shared_genres_and_nearby_release_year() -> None:
    source = RecommendationSource(
        title="Dark",
        media_type="show",
        year=2017,
        genres=["Drama", "Mystery"],
        rating=9,
        play_count=5,
        watched_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    matched = RecommendationCandidate(
        external_id=1,
        media_type="show",
        name="Matched",
        year=2018,
        poster_path="/matched.jpg",
        genre_ids=[18, 9648],
        vote_average=8,
        popularity=80,
    )
    unrelated = RecommendationCandidate(
        external_id=2,
        media_type="show",
        name="Unrelated",
        year=1980,
        genre_ids=[35],
        vote_average=6,
        popularity=20,
    )

    assert TmdbRecommendationCatalog._score_candidate(
        matched,
        source,
        {18, 9648},
    ) > TmdbRecommendationCatalog._score_candidate(
        unrelated,
        source,
        {18, 9648},
    )
