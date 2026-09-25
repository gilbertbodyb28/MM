import json
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from starlette.datastructures import UploadFile

from media_manager.auth.db import User
from media_manager.auth.users import current_active_user
from media_manager.recommendations.dependencies import (
    recommendation_config_dep,
    recommendation_service_dep,
)
from media_manager.recommendations.exceptions import (
    RecommendationConfigurationError,
    RecommendationProviderError,
    RecommendationRefreshInProgressError,
    WebhookAuthenticationError,
)
from media_manager.recommendations.schemas import (
    PlexWebhookResult,
    RecommendationRefreshResult,
    RecommendationSchema,
    RecommendationSectionCollection,
    RecommendationStatus,
)

router = APIRouter()


async def _read_plex_payload(
    request: Request,
    max_payload_bytes: int,
) -> dict[str, object]:
    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith("application/json"):
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > max_payload_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Plex webhook payload is too large",
                )
            body.extend(chunk)
        raw_payload = bytes(body)
    else:
        form = await request.form(
            max_files=1,
            max_fields=1,
            max_part_size=max_payload_bytes,
        )
        payload_part = form.get("payload")
        if isinstance(payload_part, UploadFile):
            raw_payload = await payload_part.read(max_payload_bytes + 1)
        elif isinstance(payload_part, str):
            raw_payload = payload_part.encode()
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Plex webhook form is missing its payload field",
            )
        for _field_name, part in form.multi_items():
            if isinstance(part, UploadFile) and (
                part.size is None or part.size > max_payload_bytes
            ):
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Plex webhook file is too large",
                )
    if len(raw_payload) > max_payload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Plex webhook payload is too large",
        )
    try:
        decoded = json.loads(raw_payload)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plex webhook payload must contain valid JSON",
        ) from error
    if not isinstance(decoded, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plex webhook payload must be a JSON object",
        )
    return cast(dict[str, object], decoded)


@router.get(
    "",
)
async def list_recommendations(
    recommendation_service: recommendation_service_dep,
    user: Annotated[User, Depends(current_active_user)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[RecommendationSchema]:
    return await recommendation_service.list_recommendations(user.id, limit=limit)


@router.get(
    "/status",
)
async def get_recommendation_status(
    recommendation_service: recommendation_service_dep,
    user: Annotated[User, Depends(current_active_user)],
) -> RecommendationStatus:
    return await recommendation_service.get_status(user.id)


@router.get("/sections")
async def list_recommendation_sections(
    recommendation_service: recommendation_service_dep,
    user: Annotated[User, Depends(current_active_user)],
    limit: Annotated[int, Query(ge=1, le=40)] = 20,
) -> RecommendationSectionCollection:
    return await recommendation_service.list_sections(user.id, limit=limit)


@router.post("/sections/refresh")
async def refresh_recommendation_sections(
    recommendation_service: recommendation_service_dep,
    user: Annotated[User, Depends(current_active_user)],
) -> RecommendationSectionCollection:
    try:
        return await recommendation_service.refresh_sections(user.id)
    except RecommendationConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except RecommendationProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error
    except RecommendationRefreshInProgressError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


@router.post(
    "/refresh",
)
async def refresh_recommendations(
    recommendation_service: recommendation_service_dep,
    user: Annotated[User, Depends(current_active_user)],
) -> RecommendationRefreshResult:
    try:
        return await recommendation_service.refresh_user(user.id)
    except RecommendationConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except RecommendationProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error
    except RecommendationRefreshInProgressError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


@router.post("/webhook/plex")
async def ingest_plex_webhook(
    request: Request,
    recommendation_service: recommendation_service_dep,
    recommendation_config: recommendation_config_dep,
    secret: Annotated[str | None, Query(min_length=1, max_length=500)] = None,
    webhook_secret: Annotated[
        str | None,
        Header(
            alias="X-MediaManager-Webhook-Secret",
            min_length=1,
            max_length=500,
        ),
    ] = None,
) -> PlexWebhookResult:
    supplied_secret = webhook_secret or secret
    try:
        recommendation_service.authenticate_plex_webhook(supplied_secret)
    except WebhookAuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Plex webhook authentication failed",
        ) from error

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            payload_size = int(content_length)
        except ValueError:
            payload_size = recommendation_config.max_webhook_payload_bytes + 1
        if payload_size > recommendation_config.max_webhook_payload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Plex webhook payload is too large",
            )

    payload = await _read_plex_payload(
        request,
        recommendation_config.max_webhook_payload_bytes,
    )

    try:
        return await recommendation_service.ingest_plex_webhook(
            payload,
            supplied_secret,
        )
    except WebhookAuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Plex webhook authentication failed",
        ) from error
