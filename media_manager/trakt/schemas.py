from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class TraktConnectionData(BaseModel):
    user_id: UUID
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"  # noqa: S105
    scope: str | None = None
    expires_at: datetime
    account_username: str | None = None
    account_slug: str | None = None
    trakt_user_id: str | None = None


class TraktStatus(BaseModel):
    configured: bool
    connected: bool
    username: str | None = None
    slug: str | None = None
    expires_at: datetime | None = None


class TraktAuthorizeResponse(BaseModel):
    authorization_url: str


class TraktIds(BaseModel):
    trakt: int | None = None
    slug: str | None = None
    imdb: str | None = None
    tmdb: int | None = None
    tvdb: int | None = None


class TraktMediaItem(BaseModel):
    key: str
    media_type: Literal["movie", "show"]
    title: str
    year: int | None = None
    poster_path: str | None = None
    ids: TraktIds
    sources: list[str] = Field(default_factory=list)


class TraktItemCollection(BaseModel):
    source: Literal["watchlist", "collection", "history", "lists"]
    items: list[TraktMediaItem]
    total: int = Field(ge=0)


class TraktImportItem(BaseModel):
    media_type: Literal["movie", "show"]
    tmdb_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=500)


class TraktImportRequest(BaseModel):
    items: list[TraktImportItem] = Field(min_length=1, max_length=200)

    @field_validator("items")
    @classmethod
    def unique_items(cls, value: list[TraktImportItem]) -> list[TraktImportItem]:
        unique: dict[tuple[str, int], TraktImportItem] = {}
        for item in value:
            unique.setdefault((item.media_type, item.tmdb_id), item)
        return list(unique.values())


class TraktImportResultItem(BaseModel):
    media_type: Literal["movie", "show"]
    tmdb_id: int
    title: str
    success: bool
    already_added: bool = False
    media_id: UUID | None = None
    error: str | None = None


class TraktImportResult(BaseModel):
    imported: int = Field(ge=0)
    failed: int = Field(ge=0)
    results: list[TraktImportResultItem]
