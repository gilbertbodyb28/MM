from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReleaseCalendarItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    media_type: Literal["movie", "episode"]
    media_id: UUID
    poster_id: UUID
    season_id: UUID | None = None
    name: str
    episode_title: str | None = None
    overview: str | None = None
    release_date: date
    season_number: int | None = None
    episode_number: int | None = None
    available: bool = False
