from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.core.utils.shared_future import _await_cleanup_deferring_cancellation

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _owned_response_iterator(stream: AsyncIterator[str]) -> AsyncIterator[AsyncIterator[str]]:
    try:
        yield stream
    finally:
        closing = sys.exception()
        close = getattr(stream, "aclose", None)
        if close is not None:
            try:
                cancellation = await _await_cleanup_deferring_cancellation(close())
            except Exception as failure:
                if isinstance(closing, (asyncio.CancelledError, GeneratorExit)):
                    # A close fault must not turn teardown into another SSE event.
                    logger.warning("Responses child cleanup failed during downstream teardown")
                    raise closing from failure
                raise
            if cancellation is not None:
                raise cancellation
