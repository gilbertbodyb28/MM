import re
import unicodedata
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def normalized_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^\w]+", " ", normalized).strip()


class HistorySource(StrEnum):
    TAUTULLI = "tautulli"
    PLEX = "plex"


class HistoryEventType(StrEnum):
    WATCH = "watch"
    RATING = "rating"


class RecommendationMediaType(StrEnum):
    MOVIE = "movie"
    SHOW = "show"


class SourceHistoryItem(BaseModel):
    """Provider-neutral, privacy-minimized history item used during ingestion."""

    model_config = ConfigDict(extra="ignore")

    source: HistorySource
    source_event_id: str = Field(min_length=1, max_length=128)
    source_media_id: str | None = Field(default=None, max_length=128, exclude=True)
    event_type: HistoryEventType = HistoryEventType.WATCH
    media_type: str = Field(min_length=1, max_length=32)
    title: NonEmptyText
    series_title: str | None = Field(default=None, max_length=500)
    year: int | None = Field(default=None, ge=1870, le=2200)
    genres: list[str] = Field(default_factory=list, max_length=30)
    rating: float | None = Field(default=None, ge=0, le=10)
    watched_at: datetime
    watch_duration_seconds: int | None = Field(default=None, ge=0)
    completion_percent: float | None = Field(default=None, ge=0, le=100)
    external_ids: dict[str, str] = Field(default_factory=dict, max_length=8)

    @field_validator("watched_at")
    @classmethod
    def normalize_watched_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_validator("genres")
    @classmethod
    def normalize_genres(cls, value: list[str]) -> list[str]:
        unique: dict[str, None] = {}
        for genre in value:
            cleaned = genre.strip()[:100]
            if cleaned:
                unique.setdefault(cleaned, None)
        return list(unique)[:30]

    @field_validator("external_ids")
    @classmethod
    def normalize_external_ids(cls, value: dict[str, str]) -> dict[str, str]:
        allowed = {"tmdb", "tvdb", "imdb", "plex"}
        return {
            key: cleaned
            for key, raw in value.items()
            if key in allowed and (cleaned := str(raw).strip()[:128])
        }


class SourceMetadata(BaseModel):
    genres: list[str] = Field(default_factory=list)
    rating: float | None = Field(default=None, ge=0, le=10)


class SourceStatistic(BaseModel):
    model_config = ConfigDict(extra="ignore")

    category: str = Field(min_length=1, max_length=100)
    title: NonEmptyText
    media_type: str = Field(default="unknown", max_length=32)
    play_count: int = Field(default=0, ge=0)
    duration_seconds: int = Field(default=0, ge=0)
    rating: float | None = Field(default=None, ge=0, le=10)


class PlexWebhookEvent(BaseModel):
    event: str
    account_id: str | None = None
    account_name: str | None = None
    server_id: str | None = None
    history_item: SourceHistoryItem


class RecommendationUserMappingSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    tautulli_user_id: str | None = None
    plex_account_id: str | None = None
    plex_username: str | None = None
    enabled: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class WatchHistoryItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    source: HistorySource
    source_event_id: str
    event_type: HistoryEventType = HistoryEventType.WATCH
    media_type: str
    title: str
    series_title: str | None = None
    year: int | None = None
    genres: list[str] = Field(default_factory=list)
    rating: float | None = None
    watched_at: datetime
    watch_duration_seconds: int | None = None
    completion_percent: float | None = None
    external_ids: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("watched_at", "created_at")
    @classmethod
    def normalize_timestamps(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class GeneratedRecommendation(BaseModel):
    """Strict schema sent to Ollama and used to validate its JSON response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    title: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
    ]
    media_type: Literal["movie", "show"]
    year: int | None = Field(default=None, ge=1870, le=2200)
    reason: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=10, max_length=800),
    ]
    genres: list[
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
        ]
    ] = Field(default_factory=list, max_length=10)
    confidence: float = Field(ge=0, le=1)

    @field_validator("genres")
    @classmethod
    def unique_genres(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class GeneratedRecommendationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    recommendations: list[GeneratedRecommendation] = Field(
        min_length=1,
        max_length=50,
    )


class ResolvedRecommendationMetadata(BaseModel):
    external_id: int
    metadata_provider: str
    poster_path: str | None = None
    vote_average: float | None = None
    overview: str | None = None
    added: bool = False
    id: UUID | None = None
    name: str
    year: int | None = None


class RecommendationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    recommendation_id: UUID = Field(
        default_factory=uuid4,
        validation_alias=AliasChoices("recommendation_id", "id"),
    )
    user_id: UUID = Field(exclude=True)
    name: str = Field(validation_alias=AliasChoices("name", "title"))
    media_type: RecommendationMediaType
    year: int | None = None
    external_id: int | None = None
    metadata_provider: str | None = None
    poster_path: str | None = None
    vote_average: float | None = None
    overview: str | None = None
    added: bool = False
    media_id: UUID | None = Field(default=None, serialization_alias="id")
    reason: str
    genres: list[str] = Field(default_factory=list)
    confidence: float
    rank: int = Field(ge=1)
    model_name: str
    generated_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime

    @field_validator("generated_at", "expires_at")
    @classmethod
    def normalize_recommendation_timestamps(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class SyncStateSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    source: HistorySource
    last_cursor: str | None = None
    last_sync_started_at: datetime | None = None
    last_sync_completed_at: datetime | None = None
    last_generated_at: datetime | None = None
    last_error: str | None = None
    refresh_lease_id: UUID | None = None
    refresh_lease_expires_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator(
        "last_sync_started_at",
        "last_sync_completed_at",
        "last_generated_at",
        "refresh_lease_expires_at",
        "updated_at",
    )
    @classmethod
    def normalize_optional_timestamps(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        return ensure_utc(value) if value is not None else None


class TasteHistoryEntry(BaseModel):
    title: str
    media_type: Literal["movie", "show"]
    year: int | None = None
    genres: list[str] = Field(default_factory=list)
    rating: float | None = None
    play_count: int = Field(default=1, ge=1)


class TasteProfile(BaseModel):
    watched: list[TasteHistoryEntry]
    top_genres: list[str]
    statistics: list[SourceStatistic] = Field(default_factory=list)


class ProviderSyncStatus(BaseModel):
    source: HistorySource
    last_cursor: str | None = None
    last_sync_started_at: datetime | None = None
    last_sync_completed_at: datetime | None = None
    last_generated_at: datetime | None = None
    last_error: str | None = None


class RecommendationStatus(BaseModel):
    enabled: bool
    mapped: bool
    selected_history_provider: str
    tautulli_configured: bool
    plex_configured: bool
    plex_webhook_configured: bool
    ollama_configured: bool
    history_item_count: int
    recommendation_count: int
    sync: list[ProviderSyncStatus]


class RecommendationRefreshResult(BaseModel):
    user_id: UUID
    source: HistorySource
    history_items_received: int
    history_items_inserted: int
    total_history_items: int
    recommendations_generated: int
    started_at: datetime
    completed_at: datetime
    skipped_reason: str | None = None


class LibraryMediaIdentity(BaseModel):
    media_type: Literal["movie", "show"]
    title: str
    year: int | None = None
    external_ids: dict[str, str] = Field(default_factory=dict)


class RecommendationSource(BaseModel):
    title: str
    media_type: Literal["movie", "show"]
    year: int | None = None
    genres: list[str] = Field(default_factory=list)
    rating: float | None = None
    play_count: int = Field(default=1, ge=1)
    external_ids: dict[str, str] = Field(default_factory=dict)
    watched_at: datetime

    @field_validator("watched_at")
    @classmethod
    def normalize_source_timestamp(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class RecommendationCandidate(BaseModel):
    external_id: int = Field(gt=0)
    media_type: Literal["movie", "show"]
    name: str = Field(min_length=1, max_length=300)
    year: int | None = Field(default=None, ge=1870, le=2200)
    poster_path: str | None = None
    genre_ids: list[int] = Field(default_factory=list)
    original_language: str | None = None
    vote_average: float | None = Field(default=None, ge=0, le=10)
    popularity: float | None = Field(default=None, ge=0)


class RecommendationSectionItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    recommendation_id: UUID = Field(
        default_factory=uuid4,
        validation_alias=AliasChoices("recommendation_id", "id"),
    )
    section_id: UUID = Field(exclude=True)
    name: str = Field(validation_alias=AliasChoices("name", "title"))
    media_type: RecommendationMediaType
    year: int | None = None
    external_id: int
    metadata_provider: str = "tmdb"
    poster_path: str | None = None
    added: bool = False
    media_id: UUID | None = None
    score: float = Field(ge=0)
    rank: int = Field(ge=1)


class RecommendationSectionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    section_id: UUID = Field(
        default_factory=uuid4,
        validation_alias=AliasChoices("section_id", "id"),
    )
    user_id: UUID = Field(exclude=True)
    source_title: str
    source_media_type: RecommendationMediaType
    source_year: int | None = None
    source_external_ids: dict[str, str] = Field(default_factory=dict)
    source_genres: list[str] = Field(default_factory=list)
    reason: str
    rank: int = Field(ge=1)
    candidates_considered: int = Field(default=0, ge=0, le=500)
    generated_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    items: list[RecommendationSectionItemSchema] = Field(default_factory=list)

    @field_validator("generated_at", "expires_at")
    @classmethod
    def normalize_section_timestamps(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class RecommendationSectionCollection(BaseModel):
    sections: list[RecommendationSectionSchema]
    section_count: int = Field(ge=0)
    item_count: int = Field(ge=0)
    generated_at: datetime | None = None


class PlexWebhookResult(BaseModel):
    accepted: bool
    inserted: bool = False
    refreshed: bool = False
    reason: str | None = None


class TautulliApiResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    response: dict[str, Any]


class OllamaMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str
    content: str


class OllamaChatResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str
    message: OllamaMessage
    done: bool = True
