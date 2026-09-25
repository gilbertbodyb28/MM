# ruff: noqa: S101, S106

import asyncio
from collections.abc import AsyncIterator
from io import BytesIO
from typing import Any

import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from starlette.datastructures import FormData, Headers, UploadFile
from starlette.requests import Request

from media_manager.recommendations.config import (
    PlexRecommendationConfig,
    RecommendationConfig,
)
from media_manager.recommendations.router import (
    _read_plex_payload,
    ingest_plex_webhook,
)
from media_manager.recommendations.service import RecommendationService


def webhook_config(*, max_payload_bytes: int = 1_024) -> RecommendationConfig:
    return RecommendationConfig(
        max_webhook_payload_bytes=max_payload_bytes,
        plex=PlexRecommendationConfig(
            webhook_enabled=True,
            webhook_secret=SecretStr("correct-secret"),
        ),
    )


def streaming_request(
    chunks: list[bytes],
    *,
    headers: list[tuple[bytes, bytes]],
    read_counter: list[int] | None = None,
) -> Request:
    messages = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]

    async def receive() -> dict[str, Any]:
        if read_counter is not None:
            read_counter[0] += 1
        if messages:
            return messages.pop(0)
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/recommendations/webhook/plex",
            "raw_path": b"/api/v1/recommendations/webhook/plex",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
        },
        receive,
    )


def test_webhook_authentication_happens_before_body_read() -> None:
    config = webhook_config()
    service = RecommendationService(
        repository=object(),  # type: ignore[arg-type]
        config=config,
    )
    reads = [0]
    request = streaming_request(
        [b'{"event":"library.new"}'],
        headers=[(b"content-type", b"application/json")],
        read_counter=reads,
    )

    async def exercise() -> None:
        with pytest.raises(HTTPException) as error:
            await ingest_plex_webhook(
                request,
                service,
                config,
                secret="wrong-secret",
                webhook_secret=None,
            )
        assert error.value.status_code == 401

    asyncio.run(exercise())
    assert reads == [0]


def test_webhook_header_secret_takes_precedence_and_json_streams() -> None:
    config = webhook_config()
    service = RecommendationService(
        repository=object(),  # type: ignore[arg-type]
        config=config,
    )
    reads = [0]
    request = streaming_request(
        [b'{"event":', b'"library.new"}'],
        headers=[(b"content-type", b"application/json; charset=utf-8")],
        read_counter=reads,
    )

    result = asyncio.run(
        ingest_plex_webhook(
            request,
            service,
            config,
            secret="wrong-query-secret",
            webhook_secret="correct-secret",
        )
    )
    assert result.accepted is False
    assert reads[0] == 2


def test_streamed_json_has_a_hard_total_limit() -> None:
    request = streaming_request(
        [b"12345678", b"90"],
        headers=[(b"content-type", b"application/json")],
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(_read_plex_payload(request, 8))
    assert error.value.status_code == 413


class FakeMultipartRequest:
    def __init__(self, form: FormData) -> None:
        self.headers = Headers({"content-type": "multipart/form-data; boundary=x"})
        self.form_data = form
        self.form_limits: dict[str, int] = {}

    async def form(self, **kwargs: int) -> FormData:
        self.form_limits = kwargs
        return self.form_data

    async def stream(self) -> AsyncIterator[bytes]:
        if False:
            yield b""


def test_multipart_parser_uses_tight_limits_and_rejects_large_file() -> None:
    thumbnail = UploadFile(
        file=BytesIO(b"x" * 17),
        size=17,
        filename="thumb.jpg",
    )
    request = FakeMultipartRequest(
        FormData(
            [
                ("payload", '{"event":"library.new"}'),
                ("thumb", thumbnail),
            ]
        )
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(_read_plex_payload(request, 16))  # type: ignore[arg-type]
    assert error.value.status_code == 413
    assert request.form_limits == {
        "max_files": 1,
        "max_fields": 1,
        "max_part_size": 16,
    }
