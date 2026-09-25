from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from media_manager.auth.db import User
from media_manager.auth.users import current_active_user, current_superuser
from media_manager.recommendations.dependencies import recommendation_repository_dep
from media_manager.recommendations.schemas import RecommendationUserMappingSchema
from media_manager.settings.schemas import (
    ConnectionTestResult,
    IntegrationSettingsRead,
    IntegrationSettingsUpdate,
    RecommendationMappingRead,
    RecommendationMappingUpdate,
)
from media_manager.settings.service import IntegrationSettingsService, ServiceName

router = APIRouter()


def get_settings_service() -> IntegrationSettingsService:
    return IntegrationSettingsService()


settings_service_dep = Annotated[
    IntegrationSettingsService,
    Depends(get_settings_service),
]


@router.get(
    "/integrations",
    dependencies=[Depends(current_superuser)],
)
def get_integration_settings(
    service: settings_service_dep,
) -> IntegrationSettingsRead:
    return service.get()


@router.patch(
    "/integrations",
    dependencies=[Depends(current_superuser)],
)
def update_integration_settings(
    payload: IntegrationSettingsUpdate,
    service: settings_service_dep,
) -> IntegrationSettingsRead:
    try:
        return service.update(payload)
    except (OSError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The integration settings could not be saved.",
        ) from None


@router.post(
    "/integrations/{service_name}/test",
    dependencies=[Depends(current_superuser)],
)
async def test_integration(
    service_name: ServiceName,
    service: settings_service_dep,
) -> ConnectionTestResult:
    return await service.test(service_name)


@router.get("/recommendation-mapping/me")
async def get_recommendation_mapping(
    repository: recommendation_repository_dep,
    user: Annotated[User, Depends(current_active_user)],
) -> RecommendationMappingRead:
    mapping = await repository.get_mapping(user.id)
    if mapping is None:
        return RecommendationMappingRead()
    return RecommendationMappingRead(
        tautulli_user_id=mapping.tautulli_user_id,
        plex_account_id=mapping.plex_account_id,
        plex_username=mapping.plex_username,
        enabled=mapping.enabled,
        configured=True,
    )


@router.put("/recommendation-mapping/me")
async def update_recommendation_mapping(
    payload: RecommendationMappingUpdate,
    repository: recommendation_repository_dep,
    user: Annotated[User, Depends(current_active_user)],
) -> RecommendationMappingRead:
    try:
        mapping = await repository.upsert_mapping(
            RecommendationUserMappingSchema(
                user_id=user.id,
                tautulli_user_id=payload.tautulli_user_id,
                plex_account_id=payload.plex_account_id,
                plex_username=payload.plex_username,
                enabled=payload.enabled,
            )
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That Plex or Tautulli identity is already mapped.",
        ) from None
    return RecommendationMappingRead(
        tautulli_user_id=mapping.tautulli_user_id,
        plex_account_id=mapping.plex_account_id,
        plex_username=mapping.plex_username,
        enabled=mapping.enabled,
        configured=True,
    )
