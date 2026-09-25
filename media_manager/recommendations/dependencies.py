from typing import Annotated

from fastapi import Depends

from media_manager.config import MediaManagerConfig
from media_manager.database import DbSessionDependency
from media_manager.metadataProvider.dependencies import metadata_provider_dep
from media_manager.movies.dependencies import movie_metadata_service_dep
from media_manager.recommendations.config import RecommendationConfig
from media_manager.recommendations.metadata import RecommendationMetadataResolver
from media_manager.recommendations.repository import RecommendationRepository
from media_manager.recommendations.service import RecommendationService
from media_manager.tv.dependencies import tv_metadata_service_dep


def get_recommendation_config() -> RecommendationConfig:
    return MediaManagerConfig().recommendations


recommendation_config_dep = Annotated[
    RecommendationConfig,
    Depends(get_recommendation_config),
]


def get_recommendation_repository(
    db_session: DbSessionDependency,
) -> RecommendationRepository:
    return RecommendationRepository(db_session)


recommendation_repository_dep = Annotated[
    RecommendationRepository,
    Depends(get_recommendation_repository),
]


def get_recommendation_metadata_resolver(
    metadata_provider: metadata_provider_dep,
    movie_metadata_service: movie_metadata_service_dep,
    tv_metadata_service: tv_metadata_service_dep,
) -> RecommendationMetadataResolver:
    return RecommendationMetadataResolver(
        metadata_provider=metadata_provider,
        movie_metadata_service=movie_metadata_service,
        tv_metadata_service=tv_metadata_service,
    )


recommendation_metadata_resolver_dep = Annotated[
    RecommendationMetadataResolver,
    Depends(get_recommendation_metadata_resolver),
]


def get_recommendation_service(
    repository: recommendation_repository_dep,
    config: recommendation_config_dep,
    metadata_resolver: recommendation_metadata_resolver_dep,
) -> RecommendationService:
    return RecommendationService(
        repository=repository,
        config=config,
        metadata_resolver=metadata_resolver.resolve,
    )


recommendation_service_dep = Annotated[
    RecommendationService,
    Depends(get_recommendation_service),
]
