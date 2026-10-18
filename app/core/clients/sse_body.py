from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Protocol

import aiohttp
from aiohttp.http_exceptions import TransferEncodingError

from app.core.utils.request_id import get_request_id

logger = logging.getLogger(__name__)


class SSEBody(Protocol):
    def iter_chunked(self, size: int, /) -> AsyncIterator[bytes]: ...


async def iter_sse_body_chunks(content: SSEBody, size: int) -> AsyncIterator[bytes]:
    try:
        async for chunk in content.iter_chunked(size):
            yield chunk
    except aiohttp.ClientPayloadError as exc:
        cause = exc.__cause__
        if (
            isinstance(content, aiohttp.StreamReader)
            and isinstance(cause, TransferEncodingError)
            and cause.message == "Not enough data to satisfy transfer length header."
        ):
            logger.warning(
                "upstream_sse_incomplete_transfer request_id=%s received_body_bytes=%d buffered_body_bytes=%d",
                get_request_id(),
                content.total_bytes,
                content._size,
            )
            # aiohttp's public reads raise before draining received bytes. Its
            # internal read preserves offsets, flow control and timeout checks;
            # the failed read has already settled, so there is no second reader.
            # Never clear the exception: without a validated SSE terminal the
            # consumer must still receive this original transfer failure.
            while chunk := content._read_nowait(size):
                yield chunk
        raise
