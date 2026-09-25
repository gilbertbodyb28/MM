from media_manager.metadataProvider.abstract_metadata_provider import (
    AbstractMetadataProvider,
)
from media_manager.movies.metadata import MovieMetadataService
from media_manager.recommendations.schemas import (
    GeneratedRecommendation,
    ResolvedRecommendationMetadata,
    normalized_title,
)
from media_manager.tv.metadata import TvMetadataService


class RecommendationMetadataResolver:
    """Resolves validated Ollama titles through Media Manager's metadata provider."""

    def __init__(
        self,
        metadata_provider: AbstractMetadataProvider,
        movie_metadata_service: MovieMetadataService,
        tv_metadata_service: TvMetadataService,
    ) -> None:
        self.metadata_provider = metadata_provider
        self.movie_metadata_service = movie_metadata_service
        self.tv_metadata_service = tv_metadata_service

    async def resolve(
        self,
        recommendation: GeneratedRecommendation,
    ) -> ResolvedRecommendationMetadata | None:
        if recommendation.media_type == "movie":
            candidates = await self.movie_metadata_service.search_for_movie(
                recommendation.title,
                self.metadata_provider,
            )
        else:
            candidates = await self.tv_metadata_service.search_for_show(
                recommendation.title,
                self.metadata_provider,
            )
        exact_title = normalized_title(recommendation.title)
        exact_matches = [
            candidate
            for candidate in candidates
            if normalized_title(candidate.name) == exact_title
        ]
        if not exact_matches:
            return None
        candidate = (
            exact_matches[0]
            if recommendation.year is None
            else min(
                exact_matches,
                key=lambda item: (
                    abs(item.year - recommendation.year)
                    if item.year is not None
                    else 10_000
                ),
            )
        )
        return ResolvedRecommendationMetadata(
            external_id=candidate.external_id,
            metadata_provider=candidate.metadata_provider,
            poster_path=candidate.poster_path,
            vote_average=candidate.vote_average,
            overview=candidate.overview,
            added=candidate.added,
            id=candidate.id,
            name=candidate.name,
            year=candidate.year,
        )
