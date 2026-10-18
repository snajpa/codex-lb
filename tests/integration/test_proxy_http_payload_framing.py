from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import aiohttp
import pytest

import app.core.clients.codex as codex_module
import app.core.clients.proxy as proxy_module
from app.core.openai.requests import ResponsesRequest
from app.core.upstream_proxy import ResolvedProxyEndpoint, ResolvedUpstreamRoute

pytestmark = pytest.mark.integration


@asynccontextmanager
async def _early_close_upstream(
    kind: str, padding: int, proper_http_end: bool, *, disconnected: asyncio.Event | None = None
) -> AsyncIterator[str]:
    writers: set[asyncio.StreamWriter] = set()
    tasks: set[asyncio.Task[None]] = set()

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        tasks.add(task)
        writers.add(writer)
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            length = next(
                (
                    int(line.split(b":", 1)[1])
                    for line in head.split(b"\r\n")
                    if line.lower().startswith(b"content-length:")
                ),
                0,
            )
            await reader.readexactly(length)
            if kind == "pending":
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\n\r\n"
                )
                await writer.drain()
                await reader.read()
                assert disconnected is not None
                disconnected.set()
                return
            response: dict[str, object] = {
                "id": "resp_buffered",
                "object": "response",
                "status": "completed",
                "model": "gpt-5.4",
                "output": [
                    {
                        "id": "msg_buffered",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": "x" * padding, "annotations": []}],
                    }
                ],
                "usage": {
                    "input_tokens": 128,
                    "output_tokens": 1,
                    "total_tokens": 129,
                    "input_tokens_details": {"cached_tokens": 64},
                },
            }
            created = {
                "type": "response.created",
                "response": {"id": "resp_buffered", "status": "in_progress", "output": []},
            }
            body = ("data: " + json.dumps(created) + "\n\n").encode()
            if kind == "failed":
                response.update(status="failed", error={"code": "server_error", "message": "x" * padding})
                event = {"type": "response.failed", "response": response}
            elif kind in {"malformed", "mislabeled"}:
                event = {"type": "response.completed", "response": [], "padding": "x" * padding}
            elif kind == "missing":
                event = {
                    "type": "response.output_text.delta",
                    "delta": "x" * padding,
                    "item_id": "msg_buffered",
                    "output_index": 0,
                    "content_index": 0,
                }
            else:
                event = {"type": "response.completed", "response": response}
            tail = ("data: " + json.dumps(event) + "\n\n").encode()
            if kind in {"mislabeled", "mislabeled_valid"}:
                tail = b"event: response.created\n" + tail
            body += tail[:-20] if kind == "truncated" else tail
            wire = (
                b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\n"
                b"Connection: close\r\n\r\n" + f"{len(body):x}\r\n".encode() + body + b"\r\n"
            )
            writer.write(wire + (b"0\r\n\r\n" if proper_http_end else b""))
            await writer.drain()
            if kind == "held_completed":
                await reader.read()
                assert disconnected is not None
                disconnected.set()
        finally:
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()
            writers.discard(writer)
            tasks.discard(task)

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.close()
        await server.wait_closed()
        for writer in tuple(writers):
            writer.close()
        for task in tuple(tasks):
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("routed", [False, True], ids=["direct", "routed"])
@pytest.mark.parametrize(
    ("kind", "padding", "proper_http_end"),
    [
        ("completed", 32768, True),
        ("completed", 32768, False),
        ("completed", 262144, False),
        ("failed", 32768, False),
        ("missing", 32768, False),
        ("truncated", 32768, False),
    ],
)
async def test_python_stream_preserves_received_terminal(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    routed: bool,
    kind: str,
    padding: int,
    proper_http_end: bool,
) -> None:
    monkeypatch.setattr(proxy_module, "discover_native_egress_client", lambda: None)
    monkeypatch.setattr(codex_module, "discover_native_egress_client", lambda: None)
    monkeypatch.setattr(proxy_module, "resolve_http_proxy_from_env", lambda _url: None)
    async with _early_close_upstream(kind, padding, proper_http_end) as upstream:
        route = (
            ResolvedUpstreamRoute(
                mode="account_bound",
                pool_id="synthetic",
                endpoint=ResolvedProxyEndpoint("synthetic", "http", "127.0.0.1", urlsplit(upstream).port or 80),
            )
            if routed
            else None
        )
        async with aiohttp.ClientSession() as session:
            stream = proxy_module.stream_responses(
                ResponsesRequest(model="gpt-5.4", instructions="synthetic framing probe", input=[], stream=True),
                {},
                "synthetic-access-token",
                "synthetic-account",
                session=session,
                base_url="http://upstream.invalid" if routed else upstream,
                upstream_stream_transport_override="http",
                route=route,
                codex_client=codex_module.CodexClient(session) if routed else None,
                allow_direct_egress=True,
                suppress_live_usage=True,
            )
            async with contextlib.aclosing(stream):
                events = [json.loads(block.split("data: ", 1)[1]) async for block in stream]
    assert events[0]["type"] == "response.created"
    if kind == "completed":
        assert [event["type"] for event in events] == ["response.created", "response.completed"]
        completed = events[-1]["response"]
        assert completed["output"][0]["content"][0]["text"] == "x" * padding
        assert completed["usage"]["input_tokens"] == 128
        assert completed["usage"]["input_tokens_details"]["cached_tokens"] == 64
        if not proper_http_end:
            diagnostics = [record for record in caplog.records if record.name == "app.core.clients.sse_body"]
            assert len(diagnostics) == 1
            assert isinstance(diagnostics[0].args, tuple) and diagnostics[0].args[2] > 0
    elif kind == "failed":
        assert events[-1]["type"] == "response.failed"
        assert events[-1]["response"]["error"]["code"] == "server_error"
    else:
        assert not any(event["type"] == "response.completed" for event in events)
        assert events[-1]["type"] == "response.failed"
        assert events[-1]["response"]["error"]["code"] == "upstream_unavailable"
        diagnostics = [record for record in caplog.records if record.name == "app.core.clients.sse_body"]
        assert len(diagnostics) == 1
        assert diagnostics[0].getMessage().startswith("upstream_sse_incomplete_transfer request_id=")
        assert "received_body_bytes=" in diagnostics[0].getMessage()
        assert "buffered_body_bytes=" in diagnostics[0].getMessage()
