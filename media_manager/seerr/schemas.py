from typing import Literal

from pydantic import BaseModel, Field, field_validator

SeerrMediaType = Literal["movie", "tv"]
SeerrState = Literal[
    "not_requested",
    "requested",
    "pending",
    "approved",
    "declined",
    "processing",
    "partially_available",
    "available",
    "unknown",
]


class SeerrConfiguredStatus(BaseModel):
    configured: bool


class SeerrMediaStatus(BaseModel):
    media_type: SeerrMediaType
    tmdb_id: int
    status: SeerrState
    request_id: int | None = None
    media_status: int | None = None
    request_status: int | None = None


class SeerrRequestCreate(BaseModel):
    media_type: SeerrMediaType
    tmdb_id: int = Field(gt=0)
    seasons: Literal["all"] | list[int] | None = None

    @field_validator("seasons")
    @classmethod
    def normalize_seasons(
        cls,
        value: Literal["all"] | list[int] | None,
    ) -> Literal["all"] | list[int] | None:
        if not isinstance(value, list):
            return value
        return sorted({season for season in value if season > 0}) or None


class SeerrRequestResult(SeerrMediaStatus):
    message: str
