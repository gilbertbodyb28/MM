from typing import Annotated, Literal
from urllib.parse import parse_qs, urlsplit

from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    StringConstraints,
    TypeAdapter,
    field_validator,
)

QbittorrentHash = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        pattern=r"^[0-9a-fA-F]{40,64}$",
    ),
]
_qbittorrent_hash_adapter = TypeAdapter(QbittorrentHash)


def validate_qbittorrent_hash(value: str) -> str:
    return _qbittorrent_hash_adapter.validate_python(value)


class QbTorrent(BaseModel):
    hash: QbittorrentHash
    name: str
    state: str
    progress: float = Field(ge=0, le=1)
    download_speed: int = Field(ge=0)
    upload_speed: int = Field(ge=0)
    eta: int | None = Field(default=None, ge=0)
    size: int = Field(ge=0)
    downloaded: int = Field(ge=0)
    uploaded: int = Field(ge=0)
    amount_left: int = Field(ge=0)
    ratio: float = Field(ge=0)
    seeds: int = Field(ge=0)
    peers: int = Field(ge=0)
    category: str
    added_on: int | None = Field(default=None, ge=0)
    completion_on: int | None = Field(default=None, ge=0)


class QbServerState(BaseModel):
    connection_status: str
    download_speed: int = Field(ge=0)
    upload_speed: int = Field(ge=0)
    total_downloaded: int = Field(ge=0)
    total_uploaded: int = Field(ge=0)
    free_space: int = Field(ge=0)


class QbSyncResponse(BaseModel):
    rid: int = Field(ge=0)
    full_update: bool
    torrents: dict[QbittorrentHash, QbTorrent]
    removed: list[QbittorrentHash]
    categories: list[str]
    server_state: QbServerState


class QbAddRequest(BaseModel):
    magnet_uri: SecretStr
    category: str | None = Field(default=None, max_length=200)

    @field_validator("category")
    @classmethod
    def normalize_category(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if any(ord(character) < 32 for character in normalized):
            msg = "Category contains invalid characters"
            raise ValueError(msg)
        return normalized


def validate_magnet_uri(value: SecretStr) -> str:
    """Validate without putting a private magnet URI in a validation response."""
    raw = value.get_secret_value().strip()
    if not raw or len(raw) > 16_384 or any(ord(character) < 32 for character in raw):
        msg = "Enter a valid magnet link"
        raise ValueError(msg)
    parsed = urlsplit(raw)
    exact_topics = parse_qs(parsed.query, keep_blank_values=True).get("xt", [])
    if parsed.scheme.lower() != "magnet" or not any(
        topic.lower().startswith(("urn:btih:", "urn:btmh:")) for topic in exact_topics
    ):
        msg = "Enter a valid BitTorrent magnet link"
        raise ValueError(msg)
    return raw


class QbActionResponse(BaseModel):
    hash: QbittorrentHash
    action: Literal["pause", "resume"]
    accepted: bool = True


class QbAddResponse(BaseModel):
    accepted: bool = True
    category: str


class QbDeleteResponse(BaseModel):
    hash: QbittorrentHash
    files_deleted: bool
