# ruff: noqa: S101

import asyncio

from media_manager.metadataProvider.schemas import MetaDataProviderSearchResult
from media_manager.recommendations.metadata import RecommendationMetadataResolver
from media_manager.recommendations.schemas import GeneratedRecommendation


class FakeMovieMetadataService:
    def __init__(self, results: list[MetaDataProviderSearchResult]) -> None:
        self.results = results

    async def search_for_movie(
        self,
        _query: str,
        _provider: object,
    ) -> list[MetaDataProviderSearchResult]:
        return self.results


class FakeTvMetadataService:
    async def search_for_show(
        self,
        _query: str,
        _provider: object,
    ) -> list[MetaDataProviderSearchResult]:
        return []


def candidate(year: int) -> MetaDataProviderSearchResult:
    return MetaDataProviderSearchResult(
        poster_path=f"https://example.test/dune-{year}.jpg",
        overview=f"Dune from {year}",
        name="Dune",
        external_id=year,
        year=year,
        metadata_provider="tmdb",
        added=False,
        vote_average=8.0,
    )


def recommendation(title: str, year: int) -> GeneratedRecommendation:
    return GeneratedRecommendation(
        title=title,
        media_type="movie",
        year=year,
        reason="A sufficiently detailed recommendation reason.",
        genres=["Science Fiction"],
        confidence=0.9,
    )


def test_metadata_resolution_uses_title_and_closest_year() -> None:
    resolver = RecommendationMetadataResolver(
        metadata_provider=object(),  # type: ignore[arg-type]
        movie_metadata_service=FakeMovieMetadataService(  # type: ignore[arg-type]
            [candidate(1984), candidate(2021)]
        ),
        tv_metadata_service=FakeTvMetadataService(),  # type: ignore[arg-type]
    )
    result = asyncio.run(resolver.resolve(recommendation("Dune", 2021)))
    assert result is not None
    assert result.external_id == 2021
    assert result.year == 2021


def test_unresolved_metadata_is_explicitly_returned_as_none() -> None:
    resolver = RecommendationMetadataResolver(
        metadata_provider=object(),  # type: ignore[arg-type]
        movie_metadata_service=FakeMovieMetadataService(  # type: ignore[arg-type]
            [candidate(2021)]
        ),
        tv_metadata_service=FakeTvMetadataService(),  # type: ignore[arg-type]
    )
    result = asyncio.run(resolver.resolve(recommendation("Another Title", 2021)))
    assert result is None
