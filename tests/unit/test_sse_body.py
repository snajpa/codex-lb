from __future__ import annotations

import asyncio

import aiohttp
import pytest
from aiohttp.base_protocol import BaseProtocol
from aiohttp.http_exceptions import TransferEncodingError

from app.core.clients.sse_body import iter_sse_body_chunks


@pytest.mark.asyncio
@pytest.mark.parametrize("close_early", [False, True])
async def test_buffered_transfer_error_preserves_bytes_and_exception(close_early: bool) -> None:
    content = aiohttp.StreamReader(BaseProtocol(asyncio.get_running_loop()), limit=128)
    body = b"already received SSE bytes"
    content.feed_data(body)
    cause = TransferEncodingError("Not enough data to satisfy transfer length header.")
    error = aiohttp.ClientPayloadError("synthetic incomplete transfer")
    error.__cause__ = cause
    content.set_exception(error, cause)
    stream = iter_sse_body_chunks(content, 5)
    assert await anext(stream) == body[:5]
    if close_early:
        await stream.aclose()
        assert content._size == len(body) - 5
    else:
        chunks = [body[:5]]
        with pytest.raises(aiohttp.ClientPayloadError) as raised:
            async for chunk in stream:
                chunks.append(chunk)
        assert b"".join(chunks) == body
        assert raised.value is error
        assert content._size == 0
    assert content.exception() is error
    assert error.__cause__ is cause
