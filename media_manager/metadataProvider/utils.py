import asyncio
from datetime import date
from pathlib import Path
from uuid import UUID

import httpx
from PIL import Image


def get_year_from_date(first_air_date: str | None) -> int | None:
    if first_air_date:
        return int(first_air_date.split("-")[0])
    return None


def parse_air_date(value: object) -> date | None:
    """Parse provider air dates while tolerating missing or malformed values."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _process_image(image_file_path: Path, content: bytes) -> None:
    image_file_path.write_bytes(content)

    original_image = Image.open(image_file_path)
    original_image.save(image_file_path.with_suffix(".avif"), quality=50)
    original_image.save(image_file_path.with_suffix(".webp"), quality=50)


async def download_poster_image(
    storage_path: Path, poster_url: str, uuid: UUID
) -> bool:
    async with httpx.AsyncClient(timeout=60.0) as client:
        res = await client.get(poster_url)

    if res.status_code == 200:
        image_file_path = storage_path.joinpath(str(uuid)).with_suffix(".jpg")
        await asyncio.to_thread(_process_image, image_file_path, res.content)
        return True
    return False
