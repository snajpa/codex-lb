from __future__ import annotations

import asyncio
import contextlib
import json
import os
import socket
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import aiohttp
import anyio
import pytest

import app.core.clients.native_egress as native_module
import app.core.clients.proxy as proxy_module
from app.core.clients.codex import CodexClient
from app.core.clients.native_egress import SubprocessNativeEgressClient
from app.core.clients.proxy import ProxyResponseError, compact_responses, override_stream_timeouts, stream_responses
from app.core.openai.models import CompactResponsePayload
from app.core.openai.requests import ResponsesCompactRequest, ResponsesRequest
from app.core.upstream_proxy import ResolvedProxyEndpoint, ResolvedUpstreamRoute

pytestmark = pytest.mark.integration

type _HttpHandler = Callable[[asyncio.StreamReader, asyncio.StreamWriter, bytes, bytes], Awaitable[None]]


class _UnexpectedPythonSession:
    closed = False

    async def close(self) -> None:
        self.closed = True

    async def request(self, *_args: object, **_kwargs: object) -> object:
        raise AssertionError("routed native HTTP must not use aiohttp")

    def post(self, *_args: object, **_kwargs: object) -> object:
        raise AssertionError("direct native HTTP must not use aiohttp")

    def ws_connect(self, *_args: object, **_kwargs: object) -> object:
        raise AssertionError("direct native HTTP must not use aiohttp websocket")


async def _read_request(reader: asyncio.StreamReader) -> tuple[bytes, bytes]:
    head = await reader.readuntil(b"\r\n\r\n")
    content_length = 0
    for line in head.split(b"\r\n")[1:]:
        name, separator, value = line.partition(b":")
        if separator and name.lower() == b"content-length":
            content_length = int(value.strip())
            break
    return head, await reader.readexactly(content_length)


async def _start_chunked_response(
    writer: asyncio.StreamWriter,
    *,
    status: str = "200 OK",
    content_type: str | None = "text/event-stream",
) -> None:
    content_type_header = f"Content-Type: {content_type}\r\n" if content_type is not None else ""
    writer.write(
        (
            f"HTTP/1.1 {status}\r\n" + content_type_header + "Transfer-Encoding: chunked\r\n"
            "Connection: keep-alive\r\n"
            "\r\n"
        ).encode("ascii")
    )
    await writer.drain()


async def _write_chunk(writer: asyncio.StreamWriter, chunk: bytes) -> None:
    writer.write(f"{len(chunk):x}\r\n".encode("ascii") + chunk + b"\r\n")
    await writer.drain()


async def _finish_chunks(writer: asyncio.StreamWriter) -> None:
    writer.write(b"0\r\n\r\n")
    await writer.drain()


@asynccontextmanager
async def _serve_http(handler: _HttpHandler) -> AsyncIterator[str]:
    connections: set[asyncio.StreamWriter] = set()
    tasks: set[asyncio.Task[None]] = set()

    async def dispatch(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        tasks.add(task)
        connections.add(writer)
        try:
            head, body = await _read_request(reader)
            await handler(reader, writer, head, body)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            connections.discard(writer)
            tasks.discard(task)
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()

    server = await asyncio.start_server(dispatch, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.close()
        await server.wait_closed()
        for writer in tuple(connections):
            writer.close()
        for task in tuple(tasks):
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


@pytest.fixture
async def native_worker() -> AsyncIterator[SubprocessNativeEgressClient]:
    helper_value = os.environ.get("CODEX_LB_NATIVE_EGRESS_TEST_BINARY")
    if not helper_value:
        pytest.skip("set CODEX_LB_NATIVE_EGRESS_TEST_BINARY to run the native SSE wire probes")
    helper = Path(helper_value)
    if not helper.is_file() or not os.access(helper, os.X_OK):
        pytest.skip(f"native helper is unavailable: {helper}")

    client = SubprocessNativeEgressClient(helper)
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture(autouse=True)
def direct_loopback_egress(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(proxy_module, "resolve_http_proxy_from_env", lambda _url: None)


@pytest.fixture(params=[False, True], ids=["direct", "routed"])
def routed(request: pytest.FixtureRequest) -> bool:
    return request.param


def _payload(event_block: str) -> dict[str, object]:
    data_lines = [line.removeprefix("data:").lstrip() for line in event_block.splitlines() if line.startswith("data:")]
    assert data_lines
    value = json.loads("\n".join(data_lines))
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _request(marker: str, *, stream: bool = True) -> ResponsesRequest:
    return ResponsesRequest(
        model="gpt-5.4",
        instructions="native SSE integration probe",
        input=marker,
        stream=stream,
    )


def _stream(
    base_url: str,
    native_worker: SubprocessNativeEgressClient,
    marker: str,
    *,
    stream: bool = True,
    raise_for_status: bool = False,
    routed: bool = False,
    own_codex_client: bool = False,
    payload: ResponsesRequest | None = None,
) -> AsyncIterator[str]:
    session = _UnexpectedPythonSession()
    route = (
        ResolvedUpstreamRoute(
            mode="account_bound",
            pool_id="sse-probe",
            endpoint=ResolvedProxyEndpoint("sse-proxy", "http", "127.0.0.1", urlsplit(base_url).port or 80),
        )
        if routed
        else None
    )
    return stream_responses(
        payload if payload is not None else _request(marker, stream=stream),
        {},
        "test-access-token",
        "test-account",
        base_url="http://upstream.invalid" if routed else base_url,
        raise_for_status=raise_for_status,
        session=cast(aiohttp.ClientSession, session),
        route=route,
        codex_client=CodexClient(session, native_egress_client=native_worker)
        if routed and not own_codex_client
        else None,
        upstream_stream_transport_override="http",
        allow_direct_egress=False,
        suppress_live_usage=True,
        native_egress_client=native_worker,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("response_kind", ["sse", "json", "error"])
async def test_buffered_native_burst_preserves_responses_result(
    tmp_path: Path, routed: bool, response_kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(native_module, "_NATIVE_STREAM_QUEUE_LIMIT", 64)
    handshake = json.loads(
        (Path(__file__).resolve().parents[2] / "crates/codex-lb-protocol/tests/fixtures/handshake-v1.json").read_text()
    )
    terminal = {"type": "response.completed", "response": {"id": "burst-result", "output": []}}
    expected = [{"type": "response.output_text.delta", "delta": str(index)} for index in range(256)] + [terminal]
    error = {"error": {"message": "burst error " * 256, "type": "invalid_request_error", "code": "burst_error"}}
    body = json.dumps(error if response_kind == "error" else terminal["response"])
    helper = tmp_path / "buffered-helper"
    helper.write_text(
        "#!/usr/bin/env python3\n"
        "import base64, json, sys\n"
        f"handshake = {handshake!r}\n"
        "assert json.loads(sys.stdin.readline()) == handshake['client_hello']\n"
        "print(json.dumps(handshake['server_hello']), flush=True)\n"
        "for line in sys.stdin:\n"
        "    command = json.loads(line)\n"
        "    request_id = command['request_id']\n"
        "    if command['type'] == 'cancel':\n"
        "        print(json.dumps({'type': 'cancelled', 'request_id': request_id}), flush=True)\n"
        "        continue\n"
        f"    kind, body, payloads = {response_kind!r}, {body!r}, {expected!r}\n"
        "    events = [{'type': 'head', 'status': 429 if kind == 'error' else 200,\n"
        "               'http_version': 'HTTP/2.0', 'headers': [['content-type',\n"
        "               'text/event-stream' if kind == 'sse' else 'application/json']]}]\n"
        "    if kind == 'sse':\n"
        "        events.extend({'type': 'responses_event', 'text': 'data: ' + json.dumps(payload) + '\\n\\n',\n"
        "                       'more': False, 'event_type': payload['type'], 'python_normalization': False,\n"
        "                       'stream_complete': payload['type'] == 'response.completed'}\n"
        "                      for payload in payloads)\n"
        "    else:\n"
        "        body = body.encode() + b' ' * 256\n"
        "        events.extend({'type': 'chunk', 'data': base64.b64encode(body[i:i+1]).decode()}\n"
        "                      for i in range(len(body)))\n"
        "    events.append({'type': 'end'})\n"
        "    sys.stdout.write(''.join(json.dumps(dict(event, request_id=request_id)) + '\\n' for event in events))\n"
        "    sys.stdout.flush()\n"
    )
    helper.chmod(0o700)
    client = SubprocessNativeEgressClient(helper)
    try:
        stream = _stream(
            "http://127.0.0.1:12345",
            client,
            "buffered-burst",
            stream=response_kind != "json",
            routed=routed,
            raise_for_status=True,
        )
        if response_kind == "error":
            with pytest.raises(ProxyResponseError) as exc_info:
                await asyncio.wait_for(_collect(stream), timeout=5)
            assert exc_info.value.status_code == 429
            assert exc_info.value.payload == error
        else:
            result = await asyncio.wait_for(_collect(stream), timeout=5)
            assert [_payload(event) for event in result] == (expected if response_kind == "sse" else [terminal])
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_native_proxy_frames_large_non_utf8_sse_without_python_scanning(
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
) -> None:
    comment = b": " + (b"x" * (20 * 1024)) + b"\x00\xff\xfe\xe2\x82\xac"
    raw_event = comment + b'\ndata: {"type":"response.completed","response":{"id":"resp_large"}}\n\n'
    expected_event = raw_event.decode("utf-8", errors="replace")
    assert len(raw_event) > 16 * 1024
    assert len(expected_event.encode("utf-8")) > len(raw_event)

    monkeypatch.setattr(proxy_module, "MAX_SSE_EVENT_BYTES", len(raw_event))

    def forbidden_python_scan(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Python SSE byte framing ran for a native framed response")

    monkeypatch.setattr(proxy_module, "_find_sse_separator", forbidden_python_scan)

    async def handler(
        _reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        _head: bytes,
        _body: bytes,
    ) -> None:
        await _start_chunked_response(writer)
        boundaries = (8191, 16385, len(raw_event) - 3)
        start = 0
        for end in boundaries:
            await _write_chunk(writer, raw_event[start:end])
            start = end
        await _write_chunk(writer, raw_event[start:])
        await _finish_chunks(writer)

    async with _serve_http(handler) as base_url:
        events = [event async for event in _stream(base_url, native_worker, "large-event", routed=routed)]

    assert events == [expected_event]


@pytest.mark.asyncio
@pytest.mark.parametrize("ready_count", [1, 257])
async def test_native_proxy_flushes_ready_event_before_reading_quiet_upstream(
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
    ready_count: int,
) -> None:
    ready = [
        f'data: {{"type":"response.output_text.delta","delta":"{index}"}}\n\n'.encode() for index in range(ready_count)
    ]
    completed = b'data: {"type":"response.completed","response":{"id":"resp_ready"}}\n\n'
    release_upstream = asyncio.Event()

    async def handler(
        _reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        _head: bytes,
        _body: bytes,
    ) -> None:
        await _start_chunked_response(writer)
        await _write_chunk(writer, b"".join(ready))
        await release_upstream.wait()
        await _write_chunk(writer, completed)
        await _finish_chunks(writer)

    async with _serve_http(handler) as base_url:
        events = _stream(base_url, native_worker, "ready-before-read", routed=routed)
        try:
            for block in ready:
                assert await asyncio.wait_for(anext(events), timeout=2.0) == block.decode()
            release_upstream.set()
            assert await asyncio.wait_for(_collect(events), timeout=2.0) == [completed.decode()]
        finally:
            await cast(AsyncGenerator[str, None], events).aclose()


@pytest.mark.asyncio
async def test_native_proxy_reports_public_event_size_failure(
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
) -> None:
    limit = 64
    first = b'data: {"type":"response.created"}\n\n'
    oversized = b"data: " + (b"x" * 80) + b"\n\n"
    monkeypatch.setattr(proxy_module, "MAX_SSE_EVENT_BYTES", limit)

    async def handler(
        _reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        _head: bytes,
        _body: bytes,
    ) -> None:
        await _start_chunked_response(writer)
        await _write_chunk(writer, first + oversized)
        await _finish_chunks(writer)

    async with _serve_http(handler) as base_url:
        events = [event async for event in _stream(base_url, native_worker, "oversized-event", routed=routed)]

    assert events[0] == first.decode()
    assert len(events) == 2
    failed = _payload(events[1])
    assert failed["type"] == "response.failed"
    error = cast(dict[str, object], cast(dict[str, object], failed["response"])["error"])
    assert error["code"] == "stream_event_too_large"
    assert str(len(oversized)) in cast(str, error["message"])
    assert str(limit) in cast(str, error["message"])


@pytest.mark.asyncio
async def test_native_proxy_reports_public_idle_timeout(
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
) -> None:
    worker_closed_request = asyncio.Event()

    async def handler(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        _head: bytes,
        _body: bytes,
    ) -> None:
        await _start_chunked_response(writer)
        await reader.read()
        worker_closed_request.set()

    async with _serve_http(handler) as base_url:
        with override_stream_timeouts(idle_timeout_seconds=0.1):
            events = await asyncio.wait_for(
                _collect(_stream(base_url, native_worker, "idle-timeout", routed=routed)),
                timeout=3.0,
            )
        await asyncio.wait_for(worker_closed_request.wait(), timeout=2.0)

    assert len(events) == 1
    failed = _payload(events[0])
    error = cast(dict[str, object], cast(dict[str, object], failed["response"])["error"])
    assert error["code"] == "stream_idle_timeout"
    assert error["message"] == "Upstream stream idle timeout"


async def _collect(events: AsyncIterator[str]) -> list[str]:
    return [event async for event in events]


@pytest.mark.asyncio
async def test_partial_body_activity_outlives_native_idle_interval(
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
) -> None:
    event = b'data: {"type":"response.completed","response":{"id":"resp_active"}}\n\n'
    chunks = [event[index : index + 13] for index in range(0, len(event), 13)]
    idle_timeout = 0.2

    async def handler(
        _reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        _head: bytes,
        _body: bytes,
    ) -> None:
        await _start_chunked_response(writer)
        for chunk in chunks:
            await _write_chunk(writer, chunk)
            await asyncio.sleep(0.06)
        await _finish_chunks(writer)

    async with _serve_http(handler) as base_url:
        started_at = asyncio.get_running_loop().time()
        with override_stream_timeouts(idle_timeout_seconds=idle_timeout):
            events = [event async for event in _stream(base_url, native_worker, "active-partials", routed=routed)]
        elapsed = asyncio.get_running_loop().time() - started_at

    assert elapsed > idle_timeout
    assert events == [event.decode()]


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled_scope", [False, True])
async def test_cancelling_native_stream_after_partial_event_keeps_peer_request_usable(
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
    cancelled_scope: bool,
) -> None:
    cancelled_partial_sent = asyncio.Event()
    cancelled_connection_closed = asyncio.Event()
    peer_waiting = asyncio.Event()
    release_peer = asyncio.Event()
    first = b'data: {"type":"response.created","response":{"id":"resp_cancel"}}\n\n'
    peer_completed = b'data: {"type":"response.completed","response":{"id":"resp_peer"}}\n\n'

    async def handler(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        _head: bytes,
        body: bytes,
    ) -> None:
        await _start_chunked_response(writer)
        if b"cancel-after-partial" in body:
            await _write_chunk(writer, first)
            await _write_chunk(writer, b'data: {"type":"response.output_text.delta"')
            cancelled_partial_sent.set()
            await reader.read()
            cancelled_connection_closed.set()
            return

        assert b"unrelated-peer" in body
        peer_waiting.set()
        await release_peer.wait()
        await _write_chunk(writer, peer_completed)
        await _finish_chunks(writer)

    async with _serve_http(handler) as base_url:
        cancelled = _stream(base_url, native_worker, "cancel-after-partial", routed=routed)
        assert await asyncio.wait_for(anext(cancelled), timeout=2.0) == first.decode()
        await asyncio.wait_for(cancelled_partial_sent.wait(), timeout=2.0)

        peer_task = asyncio.create_task(
            _collect(_stream(base_url, native_worker, "unrelated-peer", routed=routed)),
            name="native-sse-peer-request",
        )
        try:
            await asyncio.wait_for(peer_waiting.wait(), timeout=2.0)
            helper_process = native_worker._process

            with anyio.CancelScope() as scope:
                if cancelled_scope:
                    scope.cancel()
                await cast(AsyncGenerator[str, None], cancelled).aclose()
            await asyncio.wait_for(cancelled_connection_closed.wait(), timeout=2.0)
            release_peer.set()
            peer_events = await asyncio.wait_for(peer_task, timeout=2.0)
        finally:
            release_peer.set()
            if not peer_task.done():
                peer_task.cancel()
            await asyncio.gather(peer_task, return_exceptions=True)
            await cast(AsyncGenerator[str, None], cancelled).aclose()

    assert peer_events == [peer_completed.decode()]
    assert native_worker._process is helper_process
    assert helper_process is not None and helper_process.returncode is None


@pytest.mark.asyncio
async def test_native_streaming_http_error_body_stays_raw(
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
) -> None:
    upstream_error = {
        "error": {
            "message": "wire error body",
            "type": "invalid_request_error",
            "code": "wire_error",
        }
    }
    body = json.dumps(upstream_error, separators=(",", ":")).encode()

    def forbidden_python_scan(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("an HTTP error body must not enter SSE framing")

    monkeypatch.setattr(proxy_module, "_find_sse_separator", forbidden_python_scan)

    async def handler(
        _reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        _head: bytes,
        _request_body: bytes,
    ) -> None:
        await _start_chunked_response(writer, status="429 Too Many Requests", content_type="application/json")
        await _write_chunk(writer, body[:11])
        await _write_chunk(writer, body[11:])
        await _finish_chunks(writer)

    async with _serve_http(handler) as base_url:
        with pytest.raises(ProxyResponseError) as exc_info:
            _ = [
                event
                async for event in _stream(
                    base_url,
                    native_worker,
                    "raw-http-error",
                    raise_for_status=True,
                    routed=routed,
                )
            ]

    assert exc_info.value.status_code == 429
    assert exc_info.value.payload == upstream_error


@pytest.mark.asyncio
async def test_native_non_streaming_response_body_stays_raw(
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
) -> None:
    response = {
        "id": "resp_nonstream",
        "object": "response",
        "status": "completed",
        "output": [],
    }
    body = json.dumps(response, separators=(",", ":")).encode()
    requests: list[tuple[bytes, bytes]] = []

    def forbidden_python_scan(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a non-streaming response must not enter SSE framing")

    monkeypatch.setattr(proxy_module, "_find_sse_separator", forbidden_python_scan)

    async def handler(
        _reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        head: bytes,
        request_body: bytes,
    ) -> None:
        requests.append((head, request_body))
        await _start_chunked_response(writer, content_type="application/json")
        await _write_chunk(writer, body[:17])
        await _write_chunk(writer, body[17:])
        await _finish_chunks(writer)

    async with _serve_http(handler) as base_url:
        events = [
            event async for event in _stream(base_url, native_worker, "raw-nonstream", stream=False, routed=routed)
        ]

    assert len(requests) == 1
    assert b"accept: application/json\r\n" in requests[0][0].lower()
    assert json.loads(requests[0][1])["stream"] is False
    assert _payload(events[0]) == {"type": "response.completed", "response": response}


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["completed", "oversize", "idle", "disconnect"])
async def test_routed_native_selection_stops_after_response_head(
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    outcome: str,
) -> None:
    accepted_heads: list[bytes] = []
    unexpected_replays: list[bytes] = []
    completed = b'data: {"type":"response.completed","response":{"id":"resp_fallback"}}\n\n'
    monkeypatch.setattr(proxy_module, "MAX_SSE_EVENT_BYTES", 128)
    session = _UnexpectedPythonSession()
    monkeypatch.setattr(proxy_module, "create_codex_session", lambda: session)

    async def selected_handler(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter, head: bytes, _body: bytes
    ) -> None:
        accepted_heads.append(head)
        await _start_chunked_response(writer)
        if outcome == "completed":
            await _write_chunk(writer, completed)
            await _finish_chunks(writer)
        elif outcome == "oversize":
            await _write_chunk(writer, b"data: " + b"x" * 256)
        elif outcome == "idle":
            await reader.read()
        # Closing an unfinished chunked body produces a post-head body failure.

    async def replay_handler(
        _reader: asyncio.StreamReader, writer: asyncio.StreamWriter, head: bytes, _body: bytes
    ) -> None:
        unexpected_replays.append(head)
        await _start_chunked_response(writer)
        await _write_chunk(writer, completed)
        await _finish_chunks(writer)

    async with _serve_http(selected_handler) as selected_url, _serve_http(replay_handler) as replay_url:
        with socket.socket() as unavailable:
            # Reserve a non-listening port: a deterministic refused connection
            # proves pre-dispatch fallback without relying on external hosts.
            unavailable.bind(("127.0.0.1", 0))
            dead_port = unavailable.getsockname()[1]
            for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
                monkeypatch.setenv(name, f"http://127.0.0.1:{dead_port}")
            monkeypatch.setenv("NO_PROXY", "*")
            monkeypatch.setenv("no_proxy", "*")
            route = ResolvedUpstreamRoute(
                mode="account_bound",
                pool_id="fallback-pool",
                endpoint=ResolvedProxyEndpoint("refused", "http", "127.0.0.1", dead_port),
                fallbacks=(
                    ResolvedProxyEndpoint("selected", "http", "127.0.0.1", urlsplit(selected_url).port or 80),
                    ResolvedProxyEndpoint("no-replay", "http", "127.0.0.1", urlsplit(replay_url).port or 80),
                ),
            )
            trace = proxy_module.UpstreamProxyRouteTrace()
            with override_stream_timeouts(idle_timeout_seconds=0.15):
                events = await asyncio.wait_for(
                    _collect(
                        stream_responses(
                            _request("selected-endpoint"),
                            {},
                            "test-access-token",
                            "test-account",
                            base_url="http://upstream.invalid",
                            route=route,
                            route_trace=trace,
                            session=cast(aiohttp.ClientSession, session),
                            upstream_stream_transport_override="http",
                            suppress_live_usage=True,
                            native_egress_client=native_worker,
                        )
                    ),
                    timeout=3,
                )

    assert len(accepted_heads) == 1
    assert accepted_heads[0].startswith(b"POST http://upstream.invalid/codex/responses ")
    assert not unexpected_replays
    assert trace == proxy_module.UpstreamProxyRouteTrace("account_bound", "fallback-pool", "selected", True)
    assert session.closed
    assert not native_worker._streams
    if outcome == "completed":
        assert events == [completed.decode()]
    else:
        error = cast(dict[str, object], cast(dict[str, object], _payload(events[-1])["response"])["error"])
        assert (
            error["code"]
            == {"oversize": "stream_event_too_large", "idle": "stream_idle_timeout", "disconnect": "upstream_error"}[
                outcome
            ]
        )


@pytest.mark.asyncio
async def test_routed_missing_helper_uses_python_parser_on_resolved_proxy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing = SubprocessNativeEgressClient(tmp_path / "missing-native-helper")
    completed = b'data: {"type":"response.completed","response":{"id":"resp_python"}}\n\n'
    hits: list[bytes] = []
    scan_count = 0
    original_scan = proxy_module._find_sse_separator

    def count_scan(buffer: bytes | bytearray, start: int = 0) -> tuple[int, int] | None:
        nonlocal scan_count
        scan_count += 1
        return original_scan(buffer, start)

    monkeypatch.setattr(proxy_module, "_find_sse_separator", count_scan)

    async def handler(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter, head: bytes, _body: bytes) -> None:
        hits.append(head)
        await _start_chunked_response(writer)
        await _write_chunk(writer, completed)
        await _finish_chunks(writer)

    async with _serve_http(handler) as proxy_url, aiohttp.ClientSession(trust_env=False) as session:
        route = ResolvedUpstreamRoute(
            mode="account_bound",
            pool_id="python-fallback",
            endpoint=ResolvedProxyEndpoint("python-proxy", "http", "127.0.0.1", urlsplit(proxy_url).port or 80),
        )
        trace = proxy_module.UpstreamProxyRouteTrace()
        client = CodexClient(session, native_egress_client=missing)
        events = [
            event
            async for event in stream_responses(
                _request("missing-helper"),
                {},
                "test-access-token",
                "test-account",
                base_url="http://upstream.invalid",
                route=route,
                route_trace=trace,
                codex_client=client,
                session=session,
                upstream_stream_transport_override="http",
                suppress_live_usage=True,
            )
        ]
    assert events == [completed.decode()]
    assert scan_count > 0
    assert len(hits) == 1
    assert hits[0].startswith(b"POST http://upstream.invalid/codex/responses ")
    assert trace == proxy_module.UpstreamProxyRouteTrace("account_bound", "python-fallback", "python-proxy", False)
    assert missing._process is None


@pytest.mark.asyncio
async def test_routed_owned_client_finishes_closing_in_cancelled_scope(
    monkeypatch: pytest.MonkeyPatch, native_worker: SubprocessNativeEgressClient
) -> None:
    class DelayedCloseSession(_UnexpectedPythonSession):
        async def close(self) -> None:
            await asyncio.sleep(0)
            await super().close()

    session = DelayedCloseSession()
    monkeypatch.setattr(proxy_module, "create_codex_session", lambda: session)
    first = b'data: {"type":"response.created","response":{"id":"resp_owned"}}\n\n'
    connection_closed = asyncio.Event()

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, _head: bytes, _body: bytes) -> None:
        await _start_chunked_response(writer)
        await _write_chunk(writer, first)
        await reader.read()
        connection_closed.set()

    async with _serve_http(handler) as base_url:
        stream = _stream(base_url, native_worker, "owned-close", routed=True, own_codex_client=True)
        try:
            assert await anext(stream) == first.decode()
            with anyio.CancelScope() as scope:
                scope.cancel()
                await cast(AsyncGenerator[str, None], stream).aclose()
            await asyncio.wait_for(connection_closed.wait(), timeout=2)
            assert session.closed
            assert not native_worker._streams
        finally:
            await cast(AsyncGenerator[str, None], stream).aclose()


def _push_compact_total_timeout_override(request: pytest.FixtureRequest, total_timeout_seconds: float | None) -> None:
    """Emulate the compact service pushing its remaining budget as the total cap.

    The finalizer runs outside the test task's context, so it clears the
    override by pushing the defaults instead of resetting the token.
    """
    proxy_module.push_compact_timeout_overrides(total_timeout_seconds=total_timeout_seconds)
    request.addfinalizer(proxy_module.push_compact_timeout_overrides)


async def _compact(
    base_url: str,
    native_worker: SubprocessNativeEgressClient,
    monkeypatch: pytest.MonkeyPatch,
    *,
    routed: bool,
    marker: str = "compact-probe",
    session: aiohttp.ClientSession | None = None,
    own_codex_client: bool = False,
    selected_route: ResolvedUpstreamRoute | None = None,
    route_trace: proxy_module.UpstreamProxyRouteTrace | None = None,
    payload: ResponsesCompactRequest | None = None,
) -> CompactResponsePayload:
    monkeypatch.setattr(
        proxy_module.get_settings(), "upstream_base_url", "http://upstream.invalid" if routed else base_url
    )
    monkeypatch.setattr(proxy_module, "discover_native_egress_client", lambda: native_worker)
    session = session if session is not None else cast(aiohttp.ClientSession, _UnexpectedPythonSession())
    route = selected_route or (
        ResolvedUpstreamRoute(
            mode="account_bound",
            pool_id="compact-probe",
            endpoint=ResolvedProxyEndpoint("compact-proxy", "http", "127.0.0.1", urlsplit(base_url).port or 80),
        )
        if routed
        else None
    )
    return await compact_responses(
        payload
        if payload is not None
        else ResponsesCompactRequest(model="gpt-5.4", instructions="Summarize.", input=marker),
        {},
        "test-access-token",
        "test-account",
        session=session,
        route=route,
        codex_client=CodexClient(session, native_egress_client=native_worker)
        if routed and not own_codex_client
        else None,
        route_trace=route_trace,
        allow_direct_egress=not routed,
    )


_COMPACT_EVENTS = (
    b'data: {"type":"response.output_item.done","output_index":0,'
    b'"item":{"type":"compaction","encrypted_content":"compact-secret"}}\r\n\r\n'
    b'data: {"type":"response.completed","response":'
    b'{"object":"response","id":"resp_compact","output":[]}}\n\n'
)

_COMPACT_CASES = json.loads(
    (Path(__file__).resolve().parents[2] / "crates/codex-lb-responses/tests/fixtures/compact-v1.json").read_text()
)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _COMPACT_CASES, ids=[case["name"] for case in _COMPACT_CASES])
async def test_native_compact_collection_matches_python_public_result(
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    tmp_path: Path,
    routed: bool,
    case: dict[str, Any],
) -> None:
    async def handler(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter, _head: bytes, _body: bytes) -> None:
        await _start_chunked_response(writer)
        body = "".join(case["blocks"]).encode()
        if body:
            await _write_chunk(writer, body)
        await _finish_chunks(writer)

    async def outcome(
        base_url: str, worker: SubprocessNativeEgressClient, session: aiohttp.ClientSession | None
    ) -> object:
        try:
            result = await _compact(base_url, worker, monkeypatch, routed=routed, session=session)
            return result.model_dump()
        except ProxyResponseError as exc:
            return exc.status_code, exc.payload, exc.failure_phase

    async with _serve_http(handler) as base_url, aiohttp.ClientSession() as session:
        missing = SubprocessNativeEgressClient(tmp_path / "missing-helper")
        expected = await outcome(base_url, missing, session)

        def forbidden_collection(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("native compact must not enter the Python collector")

        monkeypatch.setattr(proxy_module, "_compact_response_payload_from_sse", forbidden_collection)
        assert await outcome(base_url, native_worker, None) == expected
    assert not native_worker._streams


@pytest.mark.asyncio
async def test_native_compact_large_result_is_fragmented_and_stops_before_late_failure(
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
) -> None:
    monkeypatch.setattr(native_module, "_NATIVE_STREAM_QUEUE_LIMIT", 64)
    items = [{"index": i, "padding": "한글" * 4096, "integer": 10**70} for i in range(96)]
    blocks = [
        json.dumps({"type": "response.output_item.done", "output_index": i, "item": item}, ensure_ascii=False)
        for i, item in enumerate(items)
    ]
    items.append({"type": "compaction", "encrypted_content": "opaque-large"})
    blocks.append(json.dumps({"type": "response.output_item.done", "output_index": len(items) - 1, "item": items[-1]}))
    blocks.append(json.dumps({"type": "response.completed", "response": {"object": "response.compact", "id": "large"}}))
    body = "".join("data: " + block + "\n\n" for block in blocks).encode() + b"data: " + b"x" * 100_000 + b"\n\n"
    monkeypatch.setattr(proxy_module, "MAX_SSE_EVENT_BYTES", 64 * 1024)
    original_read = native_module._read_event
    fragments: list[int] = []

    async def read_event(stdout: asyncio.StreamReader) -> dict[str, object]:
        event = await original_read(stdout)
        if event.get("type") == "compact":
            fragments.append(len(str(event["text"]).encode()))
        assert event.get("type") != "sse", "compact intermediate events must stay in Rust"
        return event

    monkeypatch.setattr(native_module, "_read_event", read_event)
    closed = asyncio.Event()

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, _head: bytes, _body: bytes) -> None:
        await _start_chunked_response(writer)
        await _write_chunk(writer, body)
        await reader.read()
        closed.set()

    async with _serve_http(handler) as base_url:
        result = await asyncio.wait_for(_compact(base_url, native_worker, monkeypatch, routed=routed), timeout=5)
        await asyncio.wait_for(closed.wait(), timeout=2)
    assert result.model_extra is not None
    assert result.model_extra["output"] == items
    assert len(fragments) > 64
    assert max(fragments) <= 16 * 1024


@pytest.mark.asyncio
async def test_native_compact_escaped_surrogate_key_preserves_python_validation(
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
    tmp_path: Path,
) -> None:
    body = (
        b'data: {"type":"response.output_item.done","item":{}}\n\n'
        b'data: {"type":"response.completed","response":{"object":"response.compact","\\ud800":1}}\n\n'
    )

    async def handler(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter, _head: bytes, _body: bytes) -> None:
        await _start_chunked_response(writer)
        await _write_chunk(writer, body)
        await _finish_chunks(writer)

    async with _serve_http(handler) as base_url, aiohttp.ClientSession() as session:
        missing = SubprocessNativeEgressClient(tmp_path / "missing-helper")
        with pytest.raises(ProxyResponseError) as expected:
            await asyncio.wait_for(_compact(base_url, missing, monkeypatch, routed=routed, session=session), 2)
        with pytest.raises(ProxyResponseError) as actual:
            await asyncio.wait_for(_compact(base_url, native_worker, monkeypatch, routed=routed), 2)
        assert actual.value.status_code == expected.value.status_code == 502
        assert actual.value.payload == expected.value.payload
        assert actual.value.failure_phase == expected.value.failure_phase == "parse"
    assert not native_worker._streams


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", ["text/event-stream", "Text/Event-Stream; charset=utf-8", None, ""])
async def test_native_compact_frames_and_returns_before_body_eof(
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
    content_type: str | None,
) -> None:
    closed = asyncio.Event()
    requests: list[dict[str, object]] = []

    def forbidden_python_scan(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("compact native SSE must bypass the Python byte scanner")

    monkeypatch.setattr(proxy_module, "_find_sse_separator", forbidden_python_scan)
    monkeypatch.setattr(proxy_module, "_compact_response_payload_from_sse", forbidden_python_scan)

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, _head: bytes, body: bytes) -> None:
        requests.append(json.loads(body))
        await _start_chunked_response(writer, content_type=content_type)
        for offset in range(0, len(_COMPACT_EVENTS), 17):
            await _write_chunk(writer, _COMPACT_EVENTS[offset : offset + 17])
        await reader.read()
        closed.set()

    async with _serve_http(handler) as base_url:
        response = await asyncio.wait_for(_compact(base_url, native_worker, monkeypatch, routed=routed), timeout=2)
        await asyncio.wait_for(closed.wait(), timeout=2)
    assert response.object == "response.compaction"
    assert response.id == "resp_compact"
    assert response.model_extra is not None
    assert response.model_extra["output"][0]["encrypted_content"] == "compact-secret"
    assert len(requests) == 1
    assert requests[0]["stream"] is True
    assert requests[0]["store"] is False
    assert not native_worker._streams


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", ['application/json; profile="text/event-stream"', "text/event-stream+json"])
@pytest.mark.parametrize("missing_helper", [False, True])
async def test_compact_non_sse_media_types_keep_raw_json(
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    tmp_path: Path,
    routed: bool,
    content_type: str,
    missing_helper: bool,
) -> None:
    worker = SubprocessNativeEgressClient(tmp_path / "missing-helper") if missing_helper else native_worker
    payload = {
        "object": "response.compaction",
        "id": "compact_json",
        "padding": "x" * 512,
        "output": [{"type": "compaction", "encrypted_content": "opaque-json"}],
    }
    monkeypatch.setattr(proxy_module, "MAX_SSE_EVENT_BYTES", 128)
    hits: list[bytes] = []

    def forbidden_python_scan(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("non-SSE compact JSON must bypass SSE framing")

    monkeypatch.setattr(proxy_module, "_find_sse_separator", forbidden_python_scan)

    async def handler(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter, head: bytes, _body: bytes) -> None:
        hits.append(head)
        await _start_chunked_response(writer, content_type=content_type)
        await _write_chunk(writer, json.dumps(payload).encode())
        await _finish_chunks(writer)

    async with _serve_http(handler) as base_url, aiohttp.ClientSession(trust_env=False) as session:
        response = await _compact(
            base_url, worker, monkeypatch, routed=routed, session=session if missing_helper else None
        )
        assert response.id == payload["id"]
        assert response.model_extra is not None and response.model_extra["padding"] == payload["padding"]
    assert len(hits) == 1
    assert not worker._streams


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["json", "http_error", "terminal", "eof", "oversize", "disconnect"])
async def test_native_compact_preserves_payloads_errors_and_no_replay(
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
    outcome: str,
) -> None:
    hits: list[bytes] = []
    error = {"error": {"code": "rate_limit_exceeded", "type": "rate_limit_error", "message": "try later"}}
    json_body = {
        "object": "response.compaction",
        "id": "compact_json",
        "padding": "x" * 512,
        "output": [{"type": "compaction", "encrypted_content": "opaque-json"}],
    }
    monkeypatch.setattr(proxy_module, "MAX_SSE_EVENT_BYTES", 128)

    async def handler(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter, head: bytes, _body: bytes) -> None:
        hits.append(head)
        await _start_chunked_response(
            writer,
            status="429 Too Many Requests" if outcome == "http_error" else "200 OK",
            content_type="application/json" if outcome in {"json", "http_error"} else "text/event-stream",
        )
        if outcome == "disconnect":
            return  # An incomplete chunked body, not a clean SSE EOF.
        body = {
            "json": json.dumps(json_body).encode(),
            "http_error": json.dumps(error).encode(),
            "terminal": b"data: " + json.dumps({"type": "error", **error}).encode() + b"\n\n",
            "eof": b'data: {"type":"response.created"}\n\n',
            "oversize": b"data: " + b"x" * 150,
        }[outcome]
        await _write_chunk(writer, body)
        await _finish_chunks(writer)

    async with _serve_http(handler) as base_url:
        if outcome == "json":
            response = await _compact(base_url, native_worker, monkeypatch, routed=routed)
            assert response.id == "compact_json"
            assert response.model_extra is not None and response.model_extra["padding"] == json_body["padding"]
        else:
            with pytest.raises(ProxyResponseError) as caught:
                await _compact(base_url, native_worker, monkeypatch, routed=routed)
            exc = caught.value
            assert exc.status_code == (429 if outcome in {"http_error", "terminal"} else 502)
            assert (
                exc.payload["error"]["code"]
                == {
                    "http_error": "rate_limit_exceeded",
                    "terminal": "rate_limit_exceeded",
                    "eof": "upstream_error",
                    "oversize": "stream_event_too_large",
                    "disconnect": "upstream_unavailable",
                }[outcome]
            )
            assert not exc.retryable_same_contract
            if outcome in {"http_error", "terminal"}:
                assert exc.payload["error"] == error["error"]
            if outcome == "disconnect":
                assert exc.failure_phase == "body_read"
    assert len(hits) == 1
    assert not native_worker._streams


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["idle", "total", "active"])
async def test_native_compact_preserves_idle_and_total_deadlines(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
    mode: str,
) -> None:
    settings = proxy_module.get_settings()
    monkeypatch.setattr(settings, "stream_idle_timeout_seconds", 0.15)
    # The compact total cap is override-only (the compact service pushes the
    # remaining request budget); emulate that push for the "total" mode.
    _push_compact_total_timeout_override(request, 0.2 if mode == "total" else None)
    closed = asyncio.Event()

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, _head: bytes, _body: bytes) -> None:
        await _start_chunked_response(writer)
        if mode == "idle":
            await reader.read()
            closed.set()
            return
        for offset in range(0, len(_COMPACT_EVENTS), 30):
            await _write_chunk(writer, _COMPACT_EVENTS[offset : offset + 30])
            await asyncio.sleep(0.04)
        await reader.read()
        closed.set()

    async with _serve_http(handler) as base_url:
        started = asyncio.get_running_loop().time()
        if mode == "active":
            response = await asyncio.wait_for(_compact(base_url, native_worker, monkeypatch, routed=routed), timeout=2)
            assert response.id == "resp_compact"
            assert asyncio.get_running_loop().time() - started > 0.2
            await asyncio.wait_for(closed.wait(), timeout=2)
        else:
            with pytest.raises(ProxyResponseError) as caught:
                await asyncio.wait_for(_compact(base_url, native_worker, monkeypatch, routed=routed), timeout=2)
            assert caught.value.payload["error"]["code"] == (
                "stream_idle_timeout" if mode == "idle" else "upstream_unavailable"
            )
            assert not caught.value.retryable_same_contract
    assert not native_worker._streams


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_helper", [False, True])
async def test_compact_explicit_timeout_preserves_dedicated_idle_budget(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    tmp_path: Path,
    routed: bool,
    missing_helper: bool,
) -> None:
    worker = SubprocessNativeEgressClient(tmp_path / "missing-helper") if missing_helper else native_worker
    _push_compact_total_timeout_override(request, 1.0)
    monkeypatch.setattr(proxy_module.get_settings(), "stream_idle_timeout_seconds", 0.05)

    async def handler(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter, _head: bytes, _body: bytes) -> None:
        await _start_chunked_response(writer)
        await asyncio.sleep(0.15)
        await _write_chunk(writer, _COMPACT_EVENTS)
        await _finish_chunks(writer)

    async with _serve_http(handler) as base_url, aiohttp.ClientSession(trust_env=False) as session:
        response = await _compact(
            base_url, worker, monkeypatch, routed=routed, session=session if missing_helper else None
        )
        assert response.id == "resp_compact"
    assert not worker._streams


@pytest.mark.asyncio
async def test_native_compact_cancellation_closes_owned_resources_and_keeps_peer(
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
) -> None:
    partial = asyncio.Event()
    closed = asyncio.Event()
    peer_ready = asyncio.Event()
    release_peer = asyncio.Event()
    owned_sessions: list[_UnexpectedPythonSession] = []

    class DelayedCloseSession(_UnexpectedPythonSession):
        async def close(self) -> None:
            await asyncio.sleep(0)
            await super().close()

    def create_session() -> DelayedCloseSession:
        session = DelayedCloseSession()
        owned_sessions.append(session)
        return session

    monkeypatch.setattr(proxy_module, "create_codex_session", create_session)
    monkeypatch.setattr(
        proxy_module, "CodexClient", lambda session: CodexClient(session, native_egress_client=native_worker)
    )

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, _head: bytes, body: bytes) -> None:
        await _start_chunked_response(writer)
        if b"cancel-compact" in body:
            await _write_chunk(writer, b'data: {"type":"response.created"')
            partial.set()
            await reader.read()
            closed.set()
        else:
            peer_ready.set()
            await release_peer.wait()
            await _write_chunk(writer, _COMPACT_EVENTS)
            await _finish_chunks(writer)

    async with _serve_http(handler) as base_url:
        scope_ready: asyncio.Future[anyio.CancelScope] = asyncio.get_running_loop().create_future()

        async def cancelled_request() -> None:
            with anyio.CancelScope() as scope:
                scope_ready.set_result(scope)
                await _compact(
                    base_url, native_worker, monkeypatch, routed=routed, marker="cancel-compact", own_codex_client=True
                )

        cancelled_task = asyncio.create_task(cancelled_request())
        peer_task = asyncio.create_task(
            _compact(base_url, native_worker, monkeypatch, routed=routed, marker="peer-compact")
        )
        try:
            scope = await scope_ready
            await asyncio.wait_for(partial.wait(), timeout=2)
            await asyncio.wait_for(peer_ready.wait(), timeout=2)
            process = native_worker._process
            scope.cancel()
            await asyncio.wait_for(cancelled_task, timeout=2)
            await asyncio.wait_for(closed.wait(), timeout=2)
            assert all(session.closed for session in owned_sessions)
            release_peer.set()
            response = await asyncio.wait_for(peer_task, timeout=2)
            assert response.id == "resp_compact"
            assert native_worker._process is process
            assert process is not None and process.returncode is None
        finally:
            release_peer.set()
            for task in (cancelled_task, peer_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(cancelled_task, peer_task, return_exceptions=True)
    assert not native_worker._streams


@pytest.mark.asyncio
@pytest.mark.parametrize("http_error", [False, True])
async def test_compact_missing_helper_preserves_python_transport(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, routed: bool, http_error: bool
) -> None:
    missing = SubprocessNativeEgressClient(tmp_path / "missing-compact-helper")
    hits: list[bytes] = []
    scans = 0
    scan = proxy_module._find_sse_separator

    def count_scan(buffer: bytes | bytearray, start: int = 0) -> tuple[int, int] | None:
        nonlocal scans
        scans += 1
        return scan(buffer, start)

    monkeypatch.setattr(proxy_module, "_find_sse_separator", count_scan)

    async def handler(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter, head: bytes, _body: bytes) -> None:
        hits.append(head)
        await _start_chunked_response(
            writer,
            status="400 Bad Request" if http_error else "200 OK",
            content_type="text/plain" if http_error else "text/event-stream",
        )
        await _write_chunk(
            writer,
            b'{"error":{"code":"invalid_request_error","message":"compact input invalid"}}'
            if http_error
            else _COMPACT_EVENTS,
        )
        await _finish_chunks(writer)

    async with _serve_http(handler) as base_url, aiohttp.ClientSession(trust_env=False) as session:
        if http_error:
            with pytest.raises(ProxyResponseError) as caught:
                await _compact(base_url, missing, monkeypatch, routed=routed, session=session)
            assert caught.value.status_code == 400
            assert caught.value.payload["error"]["code"] == "invalid_request_error"
        else:
            response = await _compact(base_url, missing, monkeypatch, routed=routed, session=session)
            assert response.id == "resp_compact"
        assert not session.closed  # caller owns this session
    assert len(hits) == 1
    assert hits[0].startswith(b"POST http://upstream.invalid/" if routed else b"POST /codex/responses ")
    assert (scans > 0) is not http_error
    assert missing._process is None


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["complete", "disconnect"])
async def test_native_compact_routed_fallback_keeps_metadata_and_never_replays_accepted_post(
    monkeypatch: pytest.MonkeyPatch, native_worker: SubprocessNativeEgressClient, outcome: str
) -> None:
    accepted: list[bytes] = []
    replays: list[bytes] = []

    async def selected(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter, head: bytes, _body: bytes) -> None:
        accepted.append(head)
        await _start_chunked_response(writer)
        if outcome == "complete":
            await _write_chunk(writer, _COMPACT_EVENTS)
            await _finish_chunks(writer)

    async def replay(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter, head: bytes, _body: bytes) -> None:
        replays.append(head)
        await _start_chunked_response(writer)
        await _write_chunk(writer, _COMPACT_EVENTS)
        await _finish_chunks(writer)

    async with _serve_http(selected) as selected_url, _serve_http(replay) as replay_url:
        with socket.socket() as refused:
            refused.bind(("127.0.0.1", 0))  # reserved port without a listener
            route = ResolvedUpstreamRoute(
                mode="account_bound",
                pool_id="compact-fallback",
                endpoint=ResolvedProxyEndpoint("refused", "http", "127.0.0.1", refused.getsockname()[1]),
                fallbacks=(
                    ResolvedProxyEndpoint("selected", "http", "127.0.0.1", urlsplit(selected_url).port or 80),
                    ResolvedProxyEndpoint("replay", "http", "127.0.0.1", urlsplit(replay_url).port or 80),
                ),
            )
            trace = proxy_module.UpstreamProxyRouteTrace()
            request = _compact(
                selected_url, native_worker, monkeypatch, routed=True, selected_route=route, route_trace=trace
            )
            if outcome == "complete":
                assert (await request).id == "resp_compact"
            else:
                with pytest.raises(ProxyResponseError) as caught:
                    await request
                assert caught.value.failure_phase == "body_read"
                assert not caught.value.retryable_same_contract
    assert len(accepted) == 1
    assert not replays
    assert trace == proxy_module.UpstreamProxyRouteTrace("account_bound", "compact-fallback", "selected", True)
    assert not native_worker._streams


_STREAM_CASES = json.loads(
    (Path(__file__).resolve().parents[2] / "crates/codex-lb-responses/tests/fixtures/stream-v1.json").read_text()
)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _STREAM_CASES, ids=[case["name"] for case in _STREAM_CASES])
@pytest.mark.parametrize("sdk", [False, True])
async def test_native_stream_interpretation_matches_public_python_result(
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
    case: dict[str, Any],
    sdk: bool,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("app.core.errors.time.time", lambda: 1700000000)
    body = case["block"].encode() + b'data: {"type":"response.completed","response":{"id":"end"}}\n\n'

    async def handler(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter, _head: bytes, _body: bytes) -> None:
        await _start_chunked_response(writer)
        await _write_chunk(writer, body)
        await _finish_chunks(writer)

    async def outcome(base_url: str, worker: SubprocessNativeEgressClient, session: aiohttp.ClientSession) -> list[str]:
        route = (
            ResolvedUpstreamRoute(
                mode="account_bound",
                pool_id="stream-parity",
                endpoint=ResolvedProxyEndpoint("stream-proxy", "http", "127.0.0.1", urlsplit(base_url).port or 80),
            )
            if routed
            else None
        )
        return await _collect(
            stream_responses(
                _request("interpretation"),
                {"authorization": "Bearer test"},
                "test-access-token",
                "test-account",
                base_url="http://upstream.invalid" if routed else base_url,
                session=session,
                route=route,
                codex_client=CodexClient(session, native_egress_client=worker) if routed else None,
                upstream_stream_transport_override="http",
                allow_direct_egress=False,
                suppress_live_usage=True,
                native_egress_client=worker,
                enforce_openai_sdk_contract=sdk,
            )
        )

    async with _serve_http(handler) as base_url, aiohttp.ClientSession() as session:
        missing = SubprocessNativeEgressClient(tmp_path / "missing-helper")
        expected = await outcome(base_url, missing, session)
        assert await outcome(base_url, native_worker, session) == expected
    assert not native_worker._streams


@pytest.mark.asyncio
async def test_native_interpretation_drains_large_fragments_without_python_normalization(
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
) -> None:
    monkeypatch.setattr(native_module, "_NATIVE_STREAM_QUEUE_LIMIT", 2)
    block = 'data: {"type":"response.text.delta","delta":' + json.dumps("한글😀" * 12000) + "}\n\n"
    expected = proxy_module._normalize_sse_event_block(block)
    terminal = 'data: {"type":"response.completed","response":{"id":"done"}}\n\n'
    fragments: list[int] = []
    read = native_module._read_event

    async def record(stdout: asyncio.StreamReader) -> dict[str, object]:
        event = await read(stdout)
        if event.get("type") == "responses_event":
            fragments.append(len(str(event["text"]).encode()))
        return event

    monkeypatch.setattr(native_module, "_read_event", record)
    normalizer = proxy_module._normalize_sse_event_block
    classifier = proxy_module._normalize_stream_payload_for_http_block

    def require_native(block: str) -> str:
        assert isinstance(block, native_module.NativeResponsesEvent)
        assert not block.python_normalization
        return normalizer(block)

    def require_metadata(block: str, *, enforce_openai_sdk_contract: bool = True) -> tuple[str, str | None]:
        assert isinstance(block, native_module.NativeResponsesEvent)
        assert not block.python_normalization
        return classifier(block, enforce_openai_sdk_contract=enforce_openai_sdk_contract)

    monkeypatch.setattr(proxy_module, "_normalize_sse_event_block", require_native)
    monkeypatch.setattr(proxy_module, "_normalize_stream_payload_for_http_block", require_metadata)

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, _head: bytes, _body: bytes) -> None:
        await _start_chunked_response(writer)
        await _write_chunk(writer, (block + terminal).encode())
        await reader.read()  # Completion must release the response before EOF.

    async with _serve_http(handler) as base_url:
        result = await asyncio.wait_for(_collect(_stream(base_url, native_worker, "interpreted", routed=routed)), 5)
    assert result == [expected, terminal]
    assert len(fragments) > 2
    assert max(fragments) <= 16 * 1024
    assert not native_worker._streams


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_type", ["response.completed", "response.failed", "response.incomplete"])
@pytest.mark.parametrize("sdk", [False, True])
async def test_native_http_terminal_releases_upstream_without_python_cancel(
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
    terminal_type: str,
    sdk: bool,
) -> None:
    closed = asyncio.Event()
    terminal = (
        "data: "
        + json.dumps({"type": terminal_type, "response": {"id": "done", "output": [], "padding": "한글😀" * 5000}})
        + "\n\n"
    )
    commands: list[str] = []
    fragments: list[dict[str, object]] = []
    send = native_worker._send_command
    read = native_module._read_event

    async def record_command(*args: Any, **kwargs: Any) -> None:
        command = args[2]
        commands.append(command["type"])
        await send(*args, **kwargs)

    async def record_event(stdout: asyncio.StreamReader) -> dict[str, object]:
        event = await read(stdout)
        if event.get("type") == "responses_event":
            fragments.append(event)
        return event

    monkeypatch.setattr(native_worker, "_send_command", record_command)
    monkeypatch.setattr(native_module, "_read_event", record_event)

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, _head: bytes, _body: bytes) -> None:
        await _start_chunked_response(writer)
        # The later event would exceed the configured limit if Rust kept framing.
        await _write_chunk(writer, terminal.encode() + b"data: " + b"x" * (256 * 1024))
        with contextlib.suppress(ConnectionError):
            await reader.read()
        closed.set()

    monkeypatch.setattr(proxy_module, "MAX_SSE_EVENT_BYTES", 256 * 1024)
    async with _serve_http(handler) as base_url:
        session = _UnexpectedPythonSession()
        route = (
            ResolvedUpstreamRoute(
                mode="account_bound",
                pool_id="terminal-parity",
                endpoint=ResolvedProxyEndpoint("terminal-proxy", "http", "127.0.0.1", urlsplit(base_url).port or 80),
            )
            if routed
            else None
        )
        result = await asyncio.wait_for(
            _collect(
                stream_responses(
                    _request("terminal"),
                    {},
                    "test-access-token",
                    "test-account",
                    base_url="http://upstream.invalid" if routed else base_url,
                    session=cast(aiohttp.ClientSession, session),
                    route=route,
                    codex_client=CodexClient(cast(aiohttp.ClientSession, session), native_egress_client=native_worker)
                    if routed
                    else None,
                    upstream_stream_transport_override="http",
                    allow_direct_egress=False,
                    suppress_live_usage=True,
                    native_egress_client=native_worker,
                    enforce_openai_sdk_contract=sdk,
                )
            ),
            5,
        )
        await asyncio.wait_for(closed.wait(), 5)
    assert result == [terminal]
    assert commands == ["request"]
    assert len(fragments) > 1
    assert all("stream_complete" not in event for event in fragments[:-1])
    assert fragments[-1]["stream_complete"] is True
    assert not native_worker._streams


@pytest.mark.asyncio
async def test_native_long_event_type_uses_bounded_python_handoff(
    native_worker: SubprocessNativeEgressClient, routed: bool
) -> None:
    kind = "vendor." + "x" * (20 * 1024)
    block = f'event: {kind}\ndata: {{"type":"{kind}"}}\n\n'
    terminal = 'data: {"type":"response.completed","response":{"id":"end"}}\n\n'

    async def handler(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter, _head: bytes, _body: bytes) -> None:
        await _start_chunked_response(writer)
        await _write_chunk(writer, (block + terminal).encode())
        await _finish_chunks(writer)

    async with _serve_http(handler) as base_url:
        result = await _collect(_stream(base_url, native_worker, "long-kind", routed=routed))
    assert result == [block, terminal]
    assert isinstance(result[0], native_module.NativeResponsesEvent)
    assert result[0].event_type is None
    assert result[0].python_normalization


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["completed", "failed", "missing", "truncated"])
async def test_native_received_terminal_before_incomplete_http_end(
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
    kind: str,
) -> None:
    from tests.integration.test_proxy_http_payload_framing import _early_close_upstream

    async with _early_close_upstream(kind, 262144, False) as upstream:
        async with contextlib.aclosing(
            _stream(upstream, native_worker, "synthetic framing probe", routed=routed)
        ) as stream:
            events = [_payload(block) async for block in stream]
    if kind == "completed":
        assert [event["type"] for event in events] == ["response.created", "response.completed"]
        response = cast(dict[str, Any], events[-1]["response"])
        assert response["output"][0]["content"][0]["text"] == "x" * 262144
        assert response["usage"]["input_tokens_details"]["cached_tokens"] == 64
    elif kind == "failed":
        response = cast(dict[str, Any], events[-1]["response"])
        assert events[-1]["type"] == "response.failed"
        assert response["error"]["code"] == "server_error"
    else:
        assert not any(event["type"] == "response.completed" for event in events)
        assert events[-1]["type"] == "response.failed"


@pytest.mark.asyncio
async def test_native_compact_wire_preserves_prefix_history_and_returned_window(
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
) -> None:
    tools = [{"type": "function", "name": "read_file", "parameters": {"type": "object"}, "future": "retained"}]
    history = [{"role": "user", "content": "original-history-" + "x" * 430_000}]
    request = ResponsesCompactRequest.model_validate(
        {
            "model": "gpt-5.4",
            "instructions": "policy",
            "input": history,
            "reasoning": {"effort": "high"},
            "tools": tools,
            "parallel_tool_calls": True,
            "prompt_cache_key": "stable-native-key",
            "service_tier": "default",
        }
    )
    user = {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "retained-window"}]}
    capsule = {"type": "compaction", "encrypted_content": "opaque-native", "id": "cmp_wire"}
    reply = {
        "type": "response.completed",
        "response": {
            "id": "wire-result",
            "object": "response",
            "output": [user, capsule],
            "usage": {
                "input_tokens": 1000,
                "output_tokens": 20,
                "total_tokens": 1020,
                "input_tokens_details": {"cached_tokens": 768},
            },
        },
    }
    seen: list[dict[str, Any]] = []

    async def handler(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter, head: bytes, body: bytes) -> None:
        assert b"/codex/responses " in head.split(b"\r\n", 1)[0]
        seen.append(json.loads(body))
        await _start_chunked_response(writer)
        await _write_chunk(writer, ("data: " + json.dumps(reply) + "\n\n").encode())
        await _finish_chunks(writer)

    async with _serve_http(handler) as base_url:
        result = await _compact(base_url, native_worker, monkeypatch, routed=routed, payload=request)
    assert len(seen) == 1
    wire = seen[0]
    assert wire["input"] == [*request.input, {"type": "compaction_trigger"}]
    assert wire["tools"] == tools
    assert wire["reasoning"] == {"effort": "high"}
    assert wire["parallel_tool_calls"] is True
    assert wire["prompt_cache_key"] == "stable-native-key"
    assert result.model_dump()["output"] == [user, capsule]
    assert result.usage is not None and result.usage.input_tokens_details.cached_tokens == 768
    assert not native_worker._streams


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply_delay,expected_status,reservation_status", [(0.8, 200, "finalized"), (2.0, 502, "released")]
)
async def test_compact_api_uses_full_deadline_and_finalizes_usage(
    async_client,
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    reply_delay: float,
    expected_status: int,
    reservation_status: str,
) -> None:
    from sqlalchemy import select

    from app.db.models import ApiKeyUsageReservation, RequestLog
    from app.db.session import SessionLocal
    from tests.integration.compact_test_helpers import _make_auth_json

    auth = _make_auth_json("deadline-native", "deadline-native@example.com")
    imported = await async_client.post(
        "/api/accounts/import", files={"auth_json": ("auth.json", json.dumps(auth), "application/json")}
    )
    assert imported.status_code == 200
    settings_response = await async_client.put("/api/settings", json={"apiKeyAuthEnabled": True})
    assert settings_response.status_code == 200
    created = await async_client.post(
        "/api/api-keys/",
        json={
            "name": "deadline-key",
            "limits": [{"limitType": "total_tokens", "limitWindow": "weekly", "maxValue": 100_000}],
        },
    )
    assert created.status_code == 200
    api_key = created.json()
    settings = proxy_module.get_settings()
    monkeypatch.setattr(settings, "compact_request_budget_seconds", 1.2)
    monkeypatch.setattr(proxy_module, "discover_native_egress_client", lambda: native_worker)
    reply = {
        "type": "response.completed",
        "response": {
            "id": "deadline-response",
            "object": "response",
            "output": [{"type": "compaction", "encrypted_content": "opaque"}],
            "usage": {"input_tokens": 1000, "output_tokens": 20, "total_tokens": 1020},
        },
    }
    hits: list[dict[str, Any]] = []

    async def handler(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter, _head: bytes, body: bytes) -> None:
        hits.append(json.loads(body))
        await _start_chunked_response(writer)
        try:
            await asyncio.wait_for(_reader.read(), reply_delay)
            return
        except asyncio.TimeoutError:
            pass
        await _write_chunk(writer, ("data: " + json.dumps(reply) + "\n\n").encode())
        await _finish_chunks(writer)

    async with _serve_http(handler) as base_url:
        monkeypatch.setattr(settings, "upstream_base_url", base_url)
        response = await async_client.post(
            "/v1/responses/compact",
            headers={"authorization": "Bearer " + api_key["key"], "session_id": "deadline-session"},
            json={"model": "gpt-5.4", "instructions": "policy", "input": [{"role": "user", "content": "history"}]},
        )
    assert response.status_code == expected_status, response.text
    assert len(hits) == 1
    async with SessionLocal() as session:
        reservation = (
            await session.execute(
                select(ApiKeyUsageReservation).where(ApiKeyUsageReservation.api_key_id == api_key["id"])
            )
        ).scalar_one()
        assert reservation.status == reservation_status
        log = (
            await session.execute(select(RequestLog).where(RequestLog.session_id == "deadline-session"))
        ).scalar_one()
        assert log.request_kind == "compaction"
        if expected_status == 200:
            assert log.status == "success"
            assert log.input_tokens == 1000 and log.output_tokens == 20
        else:
            assert log.status == "error" and log.error_code == "upstream_request_timeout"
    assert not native_worker._streams


@pytest.mark.asyncio
@pytest.mark.parametrize("cancellation", ["edge", "level"])
async def test_compact_api_cancellation_joins_contended_admission_cleanup(
    async_client,
    app_instance,
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    cancellation: str,
) -> None:
    from sqlalchemy import select

    from app.db.models import ApiKeyUsageReservation
    from app.db.session import SessionLocal
    from app.modules.proxy._service import compact as compact_module
    from tests.integration.compact_test_helpers import _make_auth_json

    auth = _make_auth_json("cancel-native", "cancel-native@example.com")
    imported = await async_client.post(
        "/api/accounts/import", files={"auth_json": ("auth.json", json.dumps(auth), "application/json")}
    )
    assert imported.status_code == 200
    assert (await async_client.put("/api/settings", json={"apiKeyAuthEnabled": True})).status_code == 200
    created = await async_client.post(
        "/api/api-keys/",
        json={
            "name": "cancel-key",
            "limits": [{"limitType": "total_tokens", "limitWindow": "weekly", "maxValue": 100_000}],
        },
    )
    assert created.status_code == 200
    api_key = created.json()
    settings = proxy_module.get_settings()
    monkeypatch.setattr(proxy_module, "discover_native_egress_client", lambda: native_worker)
    started, closed, release_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    releases, pops = [], []
    pop_original = compact_module._service_pop_compact_timeout_overrides

    async def release(lease):
        if lease is not None:
            releases.append(lease)
            release_started.set()
        await release_original(lease)

    def pop(tokens):
        pops.append(tokens)
        return pop_original(tokens)

    monkeypatch.setattr(compact_module, "_service_pop_compact_timeout_overrides", pop)
    scopes = []

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, _head: bytes, _body: bytes) -> None:
        await _start_chunked_response(writer)
        started.set()
        await reader.read()
        closed.set()

    async def request():
        with anyio.CancelScope() as scope:
            scopes.append(scope)
            await async_client.post(
                "/v1/responses/compact",
                headers={"authorization": "Bearer " + api_key["key"]},
                json={"model": "gpt-5.4", "input": [{"role": "user", "content": "history"}]},
            )

    async with _serve_http(handler) as base_url:
        monkeypatch.setattr(settings, "upstream_base_url", base_url)
        task = asyncio.create_task(request())
        await asyncio.wait_for(started.wait(), 3)
        load_balancer = app_instance.state.proxy_service._load_balancer
        release_original = load_balancer.release_account_lease
        monkeypatch.setattr(load_balancer, "release_account_lease", release)
        await load_balancer._runtime_lock.acquire()
        try:
            if cancellation == "edge":
                task.cancel()
            else:
                scopes[0].cancel()
            await asyncio.wait_for(release_started.wait(), 3)
            if cancellation == "edge":
                task.cancel()
            await asyncio.sleep(0)
            assert not task.done(), "request abandoned its contended account lease"
        finally:
            load_balancer._runtime_lock.release()
        if cancellation == "edge":
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 3)
        else:
            await asyncio.wait_for(task, 3)
        await asyncio.wait_for(closed.wait(), 3)
    assert len(releases) == 1 and len(pops) == 1
    assert all(runtime.inflight_response_creates == 0 for runtime in load_balancer._runtime.values())
    async with SessionLocal() as session:
        reservation = (
            await session.execute(
                select(ApiKeyUsageReservation).where(ApiKeyUsageReservation.api_key_id == api_key["id"])
            )
        ).scalar_one()
        assert reservation.status == "released"
    assert not native_worker._streams


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("phase", "cancellation"),
    [
        (phase, cancellation)
        for phase in ("lease", "health", "settlement", "log", "response_release", "client_close", "http_lease")
        for cancellation in ("edge", "level")
    ]
    + [(phase, "deadline") for phase in ("response_release", "client_close", "http_lease")],
)
async def test_compact_completed_usage_survives_cancelled_cleanup(
    async_client,
    app_instance,
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    phase: str,
    cancellation: str,
) -> None:
    from unittest.mock import AsyncMock

    from sqlalchemy import select

    import app.core.clients.codex as codex_module
    import app.core.clients.http as http_module
    from app.db.models import ApiKeyLimit, ApiKeyUsageReservation, RequestLog
    from app.db.session import SessionLocal
    from app.modules.api_keys.service import ApiKeysService
    from app.modules.proxy._service import api_key_usage as usage_module
    from app.modules.proxy._service import compact as compact_module
    from app.modules.proxy._service.request_log import _RequestLogMixin
    from app.modules.proxy.service import ProxyService
    from tests.integration.compact_test_helpers import _make_auth_json

    auth = _make_auth_json("complete-cancel", "complete-cancel@example.com")
    imported = await async_client.post(
        "/api/accounts/import", files={"auth_json": ("auth.json", json.dumps(auth), "application/json")}
    )
    assert imported.status_code == 200
    assert (await async_client.put("/api/settings", json={"apiKeyAuthEnabled": True})).status_code == 200
    created = await async_client.post(
        "/api/api-keys/",
        json={
            "name": "completed-cancel-key",
            "limits": [{"limitType": "total_tokens", "limitWindow": "weekly", "maxValue": 100_000}],
        },
    )
    assert created.status_code == 200
    api_key = created.json()
    settings = proxy_module.get_settings()
    monkeypatch.setattr(proxy_module, "discover_native_egress_client", lambda: native_worker)
    started, respond, gated, resume, closed = (asyncio.Event() for _ in range(5))
    owners, scopes, ready_signals, finalizations = [], [], [], []
    finalization_tiers = []
    upstream_tasks = []
    release_shared_original = http_module._release_http_client
    health_errors = AsyncMock(return_value={"failure_class": "timeout"})
    if cancellation == "deadline":
        monkeypatch.setattr(compact_module, "_compact_upstream_budget_seconds", lambda remaining: 0.5)
        monkeypatch.setattr(ProxyService, "_handle_stream_error", health_errors)

    async def release_shared(managed):
        if phase == "http_lease":
            gated.set()
        await release_shared_original(managed)

    monkeypatch.setattr(http_module, "_release_http_client", release_shared)
    core_original = compact_module._service_core_compact_responses
    persist_original = _RequestLogMixin._persist_request_log
    finalize_original = ApiKeysService.finalize_usage_reservation
    ready_original = usage_module._signal_propagated_responses_service_cleanup_ready
    release_transport_original = proxy_module.release_codex_response
    close_transport_original = CodexClient.close
    transport_releases, transport_closes = [], []

    async def release_transport(response):
        transport_releases.append(response)
        if phase == "response_release":
            gated.set()
            await resume.wait()
        await release_transport_original(response)

    async def close_transport(client):
        transport_closes.append(client)
        if phase == "client_close":
            gated.set()
            await resume.wait()
        await close_transport_original(client)

    monkeypatch.setattr(proxy_module, "release_codex_response", release_transport)
    monkeypatch.setattr(CodexClient, "close", close_transport)
    monkeypatch.setattr(codex_module, "discover_native_egress_client", lambda: native_worker)

    def core():
        owners.append(asyncio.current_task())

        async def tracked_core(*args, **kwargs):
            upstream_tasks.append(asyncio.current_task())
            return await core_original()(*args, **kwargs)

        return tracked_core

    async def release(lease):
        if phase == "lease" and lease is not None:
            gated.set()
        await release_original(lease)

    async def success(account):
        if phase == "health":
            gated.set()
            await resume.wait()
        await success_original(account)

    async def finalize(self, *args, **kwargs):
        finalizations.append(args[0])
        finalization_tiers.append(kwargs.get("service_tier"))
        if phase == "settlement":
            gated.set()
            await resume.wait()
        return await finalize_original(self, *args, **kwargs)

    async def persist(self, *args, **kwargs):
        if phase == "log":
            gated.set()
            await resume.wait()
        return await persist_original(self, *args, **kwargs)

    def ready():
        ready_signals.append(True)
        ready_original()

    monkeypatch.setattr(compact_module, "_service_core_compact_responses", core)
    monkeypatch.setattr(_RequestLogMixin, "_persist_request_log", persist)
    monkeypatch.setattr(ApiKeysService, "finalize_usage_reservation", finalize)
    monkeypatch.setattr(usage_module, "_signal_propagated_responses_service_cleanup_ready", ready)
    reply = {
        "type": "response.completed",
        "response": {
            "id": "completed-cancel",
            "object": "response",
            "status": "completed",
            "service_tier": "priority",
            "output": [{"type": "compaction", "encrypted_content": "opaque"}],
            "usage": {"input_tokens": 1000, "output_tokens": 20, "total_tokens": 1020},
        },
    }

    async def handler(reader, writer, _head, _body):
        await _start_chunked_response(writer)
        started.set()
        await respond.wait()
        await _write_chunk(writer, ("data: " + json.dumps(reply) + "\n\n").encode())
        await reader.read()
        closed.set()

    async def request():
        with anyio.CancelScope() as scope:
            scopes.append(scope)
            return await async_client.post(
                "/v1/responses/compact",
                headers={
                    "authorization": "Bearer " + api_key["key"],
                    "session_id": "completed-cancel-session",
                },
                json={"model": "gpt-5.4", "input": [{"role": "user", "content": "history"}]},
            )

    async with _serve_http(handler) as base_url:
        monkeypatch.setattr(settings, "upstream_base_url", base_url)
        if phase in {"response_release", "client_close"}:
            route = ResolvedUpstreamRoute(
                mode="account_bound",
                pool_id="completed-cleanup",
                endpoint=ResolvedProxyEndpoint("completed-proxy", "http", "127.0.0.1", urlsplit(base_url).port or 80),
            )

            async def resolve_route(self, *args, **kwargs):
                return route

            monkeypatch.setattr(ProxyService, "_resolve_upstream_route_for_account", resolve_route)
        task = asyncio.create_task(request())
        await asyncio.wait_for(started.wait(), 3)
        load_balancer = app_instance.state.proxy_service._load_balancer
        release_original = load_balancer.release_account_lease
        success_original = load_balancer.record_success
        monkeypatch.setattr(load_balancer, "release_account_lease", release)
        monkeypatch.setattr(load_balancer, "record_success", success)
        if phase == "lease":
            await load_balancer._runtime_lock.acquire()
        if phase == "http_lease":
            managed = http_module._http_client
            assert managed is not None and managed.active_leases == 1
            await http_module.refresh_http_client()
            assert managed.close_requested and not managed.client.session.closed
            await http_module._http_client_lock.acquire()
        try:
            respond.set()
            await asyncio.wait_for(gated.wait(), 3)
            assert len(owners) == 1
            if phase == "log":
                assert not task.done(), "request detached the required compact log insert"
            if cancellation == "edge":
                owners[0].cancel()
                await asyncio.sleep(0)
                owners[0].cancel()
            elif cancellation == "level":
                scopes[0].cancel()
            else:

                async def deadline_cancelled():
                    while not upstream_tasks[0].cancelling():
                        await asyncio.sleep(0)

                await asyncio.wait_for(deadline_cancelled(), 2)
            if phase == "settlement":
                await asyncio.sleep(0)
                assert not ready_signals, "cleanup-ready preceded reservation persistence"
                assert not task.done(), "request abandoned atomic usage settlement"
            if phase == "log":
                await asyncio.sleep(0)
                assert not task.done(), "cancellation abandoned the required compact log insert"
            if phase in {"response_release", "client_close"}:
                await asyncio.sleep(0)
                assert not task.done(), "cancellation abandoned owned transport cleanup"
        finally:
            if phase == "lease":
                load_balancer._runtime_lock.release()
            if phase == "http_lease":
                http_module._http_client_lock.release()
            resume.set()
        if cancellation == "edge":
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 3)
        else:
            result = await asyncio.wait_for(task, 3)
            if cancellation == "deadline":
                assert result.status_code == 502
                health_errors.assert_not_awaited()
        await asyncio.wait_for(closed.wait(), 3)
        if phase == "http_lease":
            assert managed.active_leases == 0, "cancellation leaked the owned shared generation lease"

            async def generation_closed():
                while not managed.client.session.closed:
                    await asyncio.sleep(0)

            await asyncio.wait_for(generation_closed(), 2)
    async with SessionLocal() as session:
        reservation = (
            await session.execute(
                select(ApiKeyUsageReservation).where(ApiKeyUsageReservation.api_key_id == api_key["id"])
            )
        ).scalar_one()
        assert reservation.status == "finalized", "completed upstream usage was released instead of charged"
        limit = (await session.execute(select(ApiKeyLimit).where(ApiKeyLimit.api_key_id == api_key["id"]))).scalar_one()
        assert limit.current_value == 1020
        log = (
            await session.execute(select(RequestLog).where(RequestLog.session_id == "completed-cancel-session"))
        ).scalar_one()
        assert log.input_tokens == 1000 and log.output_tokens == 20
    assert len(finalizations) == 1 and len(ready_signals) == 1
    assert finalization_tiers == ["priority"]
    assert all(runtime.inflight_response_creates == 0 for runtime in load_balancer._runtime.values())
    assert not native_worker._streams
    if phase in {"response_release", "client_close"}:
        assert len(transport_releases) == 1 and len(transport_closes) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_item", [None, "not-an-item", 17, []], ids=["null", "text", "number", "array"])
async def test_native_compact_rejects_malformed_retained_item_before_sse(
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
    invalid_item: object,
) -> None:
    response = {
        "id": "compact-invalid-window",
        "output": [invalid_item, {"type": "compaction", "encrypted_content": "opaque-capsule"}],
    }
    body = ("data: " + json.dumps({"type": "response.completed", "response": response}) + "\n\n").encode()

    async def handler(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter, _head: bytes, _body: bytes) -> None:
        await _start_chunked_response(writer)
        await _write_chunk(writer, body)
        await _finish_chunks(writer)

    async with _serve_http(handler) as base_url:
        with pytest.raises(ProxyResponseError) as caught:
            await asyncio.wait_for(_compact(base_url, native_worker, monkeypatch, routed=routed), 5)
    assert caught.value.status_code == 502
    assert caught.value.payload["error"]["code"] == "invalid_compaction_response"
    assert not native_worker._streams


@pytest.mark.asyncio
@pytest.mark.parametrize("retained_type", [[], {}, None, 17], ids=["array", "object", "null", "number"])
async def test_native_compact_preserves_retained_non_string_type(
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
    retained_type: object,
) -> None:
    output = [
        {"type": retained_type, "opaque": "retained"},
        {"type": "compaction", "encrypted_content": "opaque-capsule"},
    ]
    body = (
        "data: "
        + json.dumps({"type": "response.completed", "response": {"id": "retained-type", "output": output}})
        + "\n\n"
    ).encode()

    async def handler(_reader, writer, _head, _body):
        await _start_chunked_response(writer)
        await _write_chunk(writer, body)
        await _finish_chunks(writer)

    async with _serve_http(handler) as base_url:
        result = await asyncio.wait_for(_compact(base_url, native_worker, monkeypatch, routed=routed), 5)
    assert result.output == output
    assert not native_worker._streams


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["standalone", "trigger", "bridge"])
@pytest.mark.parametrize("retained_type", [[], {}, None, 17], ids=["array", "object", "null", "number"])
async def test_compact_api_preserves_opaque_type_window_after_settlement(
    async_client,
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    surface: str,
    retained_type: object,
) -> None:
    from sqlalchemy import select

    from app.core.openai.requests import ResponsesCompactRequest, ResponsesRequest
    from app.db.models import ApiKeyLimit, ApiKeyUsageReservation, RequestLog
    from app.db.session import SessionLocal
    from app.modules.api_keys.repository import ApiKeysRepository
    from app.modules.api_keys.service import ApiKeysService, ApiKeyUsageReservationData
    from app.modules.proxy.api_key_usage import estimate_api_key_request_usage
    from app.modules.proxy.http_bridge_forwarding import HTTPBridgeForwardContext, build_owner_forward_headers
    from tests.integration.compact_test_helpers import _make_auth_json

    auth = _make_auth_json("opaque-native", "opaque-native@example.com")
    imported = await async_client.post(
        "/api/accounts/import", files={"auth_json": ("auth.json", json.dumps(auth), "application/json")}
    )
    assert imported.status_code == 200
    assert (await async_client.put("/api/settings", json={"apiKeyAuthEnabled": True})).status_code == 200
    created = await async_client.post(
        "/api/api-keys/",
        json={
            "name": "opaque-native-key",
            "limits": [{"limitType": "total_tokens", "limitWindow": "weekly", "maxValue": 100_000}],
        },
    )
    assert created.status_code == 200
    key = created.json()
    settings = proxy_module.get_settings()
    monkeypatch.setattr(proxy_module, "discover_native_egress_client", lambda: native_worker)
    output = [
        {"type": retained_type, "opaque": "retained"},
        {"type": "compaction", "id": "cmp_native_opaque", "encrypted_content": "opaque-capsule", "status": "completed"},
    ]
    reply = {
        "type": "response.completed",
        "response": {
            "id": "opaque-native",
            "object": "response",
            "output": output,
            "usage": {"input_tokens": 1000, "output_tokens": 20, "total_tokens": 1020},
        },
    }
    hits = []

    async def handler(_reader, writer, _head, body):
        hits.append(json.loads(body))
        await _start_chunked_response(writer)
        await _write_chunk(writer, ("data: " + json.dumps(reply) + "\n\n").encode())
        await _finish_chunks(writer)

    compact = ResponsesCompactRequest.model_validate(
        {"model": "gpt-5.4", "instructions": "policy", "input": [{"role": "user", "content": "history"}]}
    )
    headers = {"authorization": "Bearer " + key["key"], "session_id": "opaque-native-session"}
    wire_payload = compact.to_payload()
    path = "/backend-api/codex/responses/compact"
    if surface != "standalone":
        forwarded = ResponsesRequest.model_validate(
            {**wire_payload, "input": [*wire_payload["input"], {"type": "compaction_trigger"}], "stream": True}
        )
        wire_payload = forwarded.model_dump_for_forwarding()
        path = "/backend-api/codex/responses"
        if surface == "bridge":
            async with SessionLocal() as session:
                reservation = await ApiKeysService(ApiKeysRepository(session)).enforce_limits_for_request(
                    key["id"],
                    request_model=compact.model,
                    request_service_tier=None,
                    request_usage_budget=estimate_api_key_request_usage(compact),
                )
                assert reservation is not None
            context = HTTPBridgeForwardContext(
                origin_instance="opaque-origin",
                target_instance=settings.http_responses_session_bridge_instance_id,
                codex_session_affinity=True,
                downstream_turn_state=None,
                reservation=ApiKeyUsageReservationData(
                    reservation_id=reservation.reservation_id, key_id=key["id"], model=compact.model
                ),
            )
            headers = build_owner_forward_headers(headers=headers, payload=forwarded, context=context)
            path = "/internal/bridge/responses"
    async with _serve_http(handler) as base_url:
        monkeypatch.setattr(settings, "upstream_base_url", base_url)
        response = await asyncio.wait_for(async_client.post(path, headers=headers, json=wire_payload), 5)
    assert response.status_code == 200
    if surface == "standalone":
        assert response.json()["output"] == output
    else:
        events = [
            json.loads(line[5:])
            for line in response.text.splitlines()
            if line.startswith("data:") and line[5:].strip() != "[DONE]"
        ]
        terminal = [event for event in events if event.get("type") == "response.completed"]
        assert len(terminal) == 1 and terminal[0]["response"]["output"] == output
        added = [event for event in events if event.get("type") == "response.output_item.added"]
        done = [event for event in events if event.get("type") == "response.output_item.done"]
        assert [event["item"] for event in added] == [output[0], {**output[1], "status": "in_progress"}]
        assert [event["item"] for event in done] == output
        assert [event["output_index"] for event in added] == [0, 1]
    assert len(hits) == 1
    async with SessionLocal() as session:
        reservations = (
            (
                await session.execute(
                    select(ApiKeyUsageReservation).where(ApiKeyUsageReservation.api_key_id == key["id"])
                )
            )
            .scalars()
            .all()
        )
        assert len(reservations) == 1 and reservations[0].status == "finalized"
        limit = (await session.execute(select(ApiKeyLimit).where(ApiKeyLimit.api_key_id == key["id"]))).scalar_one()
        assert limit.current_value == 1020
        log = (
            await session.execute(select(RequestLog).where(RequestLog.session_id == "opaque-native-session"))
        ).scalar_one()
        assert log.request_kind == "compaction" and log.input_tokens == 1000 and log.output_tokens == 20
    assert not native_worker._streams


@pytest.mark.asyncio
@pytest.mark.parametrize("next_operation", ["compact", "continue"])
async def test_native_recompact_marker_history_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
    next_operation: str,
) -> None:
    window = [
        {
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": "Local compact fallback preserved the latest encrypted reasoning state.",
                }
            ],
        },
        {"type": "compaction", "id": "cmp_valid", "encrypted_content": "opaque-native-window", "status": "completed"},
    ]
    hits = []

    async def handler(_reader, writer, _head, body):
        hits.append(json.loads(body))
        await _start_chunked_response(writer)
        await _write_chunk(
            writer,
            (
                "data: "
                + json.dumps(
                    {
                        "type": "response.completed",
                        "response": {"id": "native-marker", "object": "response", "output": window},
                    }
                )
                + "\n\n"
            ).encode(),
        )
        await _finish_chunks(writer)

    settings = proxy_module.get_settings()
    monkeypatch.setattr(proxy_module, "discover_native_egress_client", lambda: native_worker)
    async with _serve_http(handler) as base_url:
        monkeypatch.setattr(settings, "upstream_base_url", base_url)
        first = await _compact(
            base_url,
            native_worker,
            monkeypatch,
            routed=routed,
            payload=ResponsesCompactRequest(model="gpt-5.4", instructions="compact", input="history"),
        )
        assert [
            item.model_dump(mode="json", exclude_none=True) if hasattr(item, "model_dump") else item
            for item in first.output
        ] == window
        if next_operation == "compact":
            second = await _compact(
                base_url,
                native_worker,
                monkeypatch,
                routed=routed,
                payload=ResponsesCompactRequest(model="gpt-5.4", instructions="compact", input=window),
            )
            assert second.output == first.output
        else:
            events = [
                event
                async for event in _stream(
                    base_url,
                    native_worker,
                    "continue-marker",
                    routed=routed,
                    payload=ResponsesRequest(model="gpt-5.4", instructions="continue", input=window, stream=True),
                )
            ]
            assert any('"response.completed"' in event for event in events)
    assert len(hits) == 2
    assert hits[1]["input"] == (window if next_operation == "continue" else [*window, {"type": "compaction_trigger"}])
    assert not native_worker._streams


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "surface,cancellation",
    [
        ("warmup", "edge"),
        ("warmup", "level"),
        ("automation", "edge"),
        ("automation", "level"),
        ("automation", "deadline"),
    ],
)
@pytest.mark.parametrize(
    "transport,phase", [("native", "response_release"), ("native", "client_close"), ("socks_json", "session_close")]
)
async def test_background_compact_completion_survives_teardown(
    async_client,
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    surface: str,
    cancellation: str,
    phase: str,
    transport: str,
) -> None:
    from unittest.mock import AsyncMock

    from sqlalchemy import select

    import app.core.clients.codex as codex_module
    import app.modules.automations.service as automation_module
    from app.db.models import AutomationRun, RequestLog
    from app.db.session import SessionLocal
    from app.modules.accounts.repository import AccountsRepository
    from app.modules.automations.repository import AutomationsRepository
    from app.modules.automations.service import AutomationsService
    from app.modules.proxy.service import ProxyService
    from app.modules.request_logs.repository import RequestLogsRepository
    from tests.integration.compact_test_helpers import _make_auth_json

    account_ids = []
    for index in range(2 if surface == "automation" else 1):
        auth = _make_auth_json(f"background-{index}", f"background-{index}@example.com")
        imported = await async_client.post(
            "/api/accounts/import", files={"auth_json": ("auth.json", json.dumps(auth), "application/json")}
        )
        assert imported.status_code == 200
        from app.core.auth import generate_unique_account_id

        account_ids.append(generate_unique_account_id(f"background-{index}", f"background-{index}@example.com"))
    monkeypatch.setattr("app.modules.proxy.work_admission.ADMISSION_WAIT_TIMEOUT_SECONDS", 0.05)
    assert (
        await async_client.put(
            "/api/settings",
            json={
                "warmupModel": "gpt-5.4-nano",
                "upstreamConnectTimeoutSeconds": 0.1,
                "compactRequestBudgetSeconds": 0.4 if cancellation == "deadline" else 5.0,
            },
        )
    ).status_code == 200
    settings = proxy_module.get_settings()
    monkeypatch.setattr(
        proxy_module, "discover_native_egress_client", lambda: native_worker if transport == "native" else None
    )
    monkeypatch.setattr(
        codex_module, "discover_native_egress_client", lambda: native_worker if transport == "native" else None
    )
    gated, resume = asyncio.Event(), asyncio.Event()
    release_original, close_original = proxy_module.release_codex_response, CodexClient.close
    hits, owners, scopes, core_tasks = [], [], [], []
    entered = 0

    async def gate_once():
        nonlocal entered
        entered += 1
        if entered == 1:
            gated.set()
            await resume.wait()

    async def release(response):
        if phase == "response_release":
            await gate_once()
        await release_original(response)

    async def close(client):
        if phase == "client_close":
            await gate_once()
        await close_original(client)

    monkeypatch.setattr(proxy_module, "release_codex_response", release)
    monkeypatch.setattr(CodexClient, "close", close)
    owned_sessions = set()
    owned_init = codex_module._SessionOwnedResponse.__init__
    session_close = aiohttp.ClientSession.close

    def track_owned_response(self, response, session):
        owned_init(self, response, session)
        owned_sessions.add(id(session))

    async def close_owned_session(session):
        if phase == "session_close" and id(session) in owned_sessions:
            await gate_once()
        await session_close(session)

    monkeypatch.setattr(codex_module._SessionOwnedResponse, "__init__", track_owned_response)
    monkeypatch.setattr(aiohttp.ClientSession, "close", close_owned_session)

    async def fresh(self, account, **_kwargs):
        return account

    monkeypatch.setattr(ProxyService, "_ensure_fresh_with_budget", fresh)
    monkeypatch.setattr(automation_module.AuthManager, "ensure_fresh", fresh)
    health = AsyncMock()
    monkeypatch.setattr(ProxyService, "_handle_proxy_error", health)
    monkeypatch.setattr(AutomationsService, "_mark_permanent_account_failure", health)
    core_original = proxy_module.compact_responses

    async def tracked_core(*args, **kwargs):
        core_tasks.append(asyncio.current_task())
        return await core_original(*args, **kwargs)

    monkeypatch.setattr(automation_module, "core_compact_responses", tracked_core)
    monkeypatch.setattr("app.modules.proxy.service.core_compact_responses", tracked_core)

    async def handler(_reader, writer, _head, body):
        hits.append(json.loads(body))
        if transport == "socks_json":
            response = {
                "id": "background-native",
                "object": "response",
                "service_tier": "priority",
                "output": [{"type": "compaction", "encrypted_content": "opaque"}],
                "usage": {"input_tokens": 1000, "output_tokens": 20, "total_tokens": 1020},
            }
            encoded = json.dumps(response).encode()
            writer.write(
                (
                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                    + str(len(encoded))
                    + "\r\nConnection: close\r\n\r\n"
                ).encode()
                + encoded
            )
            await writer.drain()
            return
        await _start_chunked_response(writer)
        await _write_chunk(
            writer,
            (
                "data: "
                + json.dumps(
                    {
                        "type": "response.completed",
                        "response": {
                            "id": "background-native",
                            "object": "response",
                            "service_tier": "priority",
                            "output": [{"type": "compaction", "encrypted_content": "opaque"}],
                            "usage": {"input_tokens": 1000, "output_tokens": 20, "total_tokens": 1020},
                        },
                    }
                )
                + "\n\n"
            ).encode(),
        )
        await _finish_chunks(writer)

    run_id = None

    async def request():
        nonlocal run_id
        owners.append(asyncio.current_task())
        with anyio.CancelScope() as scope:
            scopes.append(scope)
            if surface == "warmup":
                return await async_client.post("/v1/warmup", json={"mode": "force"})
            async with SessionLocal() as session:
                repository = AutomationsRepository(session)
                job = await repository.create_job(
                    name="native-background",
                    enabled=True,
                    schedule_type="daily",
                    schedule_time="00:00",
                    schedule_timezone="UTC",
                    schedule_days=["mon"],
                    schedule_threshold_minutes=0,
                    include_paused_accounts=False,
                    model="gpt-5.4",
                    reasoning_effort=None,
                    prompt="ping",
                    account_ids=account_ids,
                )
                from app.core.utils.time import utcnow

                now = utcnow()
                from app.core.config.dashboard_overrides import dashboard_overrides_bound
                from app.core.config.settings_cache import get_settings_cache

                with dashboard_overrides_bound(await get_settings_cache().get()):
                    run = await repository.claim_run(
                        job_id=job.id,
                        trigger="scheduled",
                        slot_key="native-background-slot",
                        cycle_key="native-background-no-cycle",
                        cycle_expected_accounts=None,
                        cycle_window_end=None,
                        scheduled_for=now,
                        started_at=now,
                    )
                    assert run is not None
                    run_id = run.id
                    service = AutomationsService(
                        repository, AccountsRepository(session), RequestLogsRepository(session)
                    )
                    return await service._execute_claimed_run(job, run)

    async with _serve_http(handler) as base_url, contextlib.AsyncExitStack() as stack:
        monkeypatch.setattr(settings, "upstream_base_url", base_url)
        route = ResolvedUpstreamRoute(
            mode="account_bound",
            pool_id="background",
            endpoint=ResolvedProxyEndpoint("background-proxy", "http", "127.0.0.1", urlsplit(base_url).port or 80),
        )

        if transport == "socks_json":
            route = await stack.enter_async_context(_serve_socks_route(base_url))

        async def resolve(*_args, **_kwargs):
            return route

        monkeypatch.setattr(ProxyService, "_resolve_upstream_route_for_account", resolve)
        monkeypatch.setattr(automation_module, "_resolve_upstream_route_for_account", resolve)
        task = asyncio.create_task(request())
        try:
            await asyncio.wait_for(gated.wait(), 3)
            if cancellation == "edge":
                owners[0].cancel()
            elif cancellation == "level":
                scopes[0].cancel()
            else:

                async def deadline_fired():
                    while not any(owner is not None and owner.cancelling() for owner in core_tasks):
                        await asyncio.sleep(0)

                await asyncio.wait_for(deadline_fired(), 2)
            await asyncio.sleep(0)
            resume.set()
            if cancellation == "edge":
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 3)
            else:
                await asyncio.wait_for(task, 3)
        finally:
            resume.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert len(hits) == 1
    health.assert_not_awaited()
    async with SessionLocal() as session:
        logs = (await session.execute(select(RequestLog).where(RequestLog.account_id.in_(account_ids)))).scalars().all()
        assert len(logs) == 1
        assert logs[0].input_tokens == 1000 and logs[0].output_tokens == 20
        assert logs[0].service_tier == "priority"
        if surface == "warmup":
            assert logs[0].request_kind == "warmup"
        else:
            run_row = (await session.execute(select(AutomationRun).where(AutomationRun.id == run_id))).scalar_one()
            assert run_row.status == "failed" and run_row.attempt_count == 1
    assert not native_worker._streams


@pytest.mark.asyncio
async def test_warmup_header_wait_uses_compact_budget(
    async_client,
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    routed: bool,
) -> None:
    from app.modules.proxy.service import ProxyService
    from tests.integration.compact_test_helpers import _make_auth_json

    auth = _make_auth_json("warmup-headers", "warmup-headers@example.com")
    imported = await async_client.post(
        "/api/accounts/import", files={"auth_json": ("auth.json", json.dumps(auth), "application/json")}
    )
    assert imported.status_code == 200
    monkeypatch.setattr("app.modules.proxy.work_admission.ADMISSION_WAIT_TIMEOUT_SECONDS", 0.05)
    assert (
        await async_client.put(
            "/api/settings",
            json={
                "warmupModel": "gpt-5.4-nano",
                "upstreamConnectTimeoutSeconds": 0.1,
                "compactRequestBudgetSeconds": 0.2,
            },
        )
    ).status_code == 200
    settings = proxy_module.get_settings()
    monkeypatch.setattr(proxy_module, "discover_native_egress_client", lambda: native_worker)
    hits, closed = [], asyncio.Event()

    async def fresh(self, account, **_kwargs):
        return account

    monkeypatch.setattr(ProxyService, "_ensure_fresh_with_budget", fresh)

    async def handler(reader, _writer, _head, body):
        hits.append(json.loads(body))
        await reader.read()
        closed.set()

    async with _serve_http(handler) as base_url:
        monkeypatch.setattr(settings, "upstream_base_url", base_url)
        route = (
            ResolvedUpstreamRoute(
                mode="account_bound",
                pool_id="headers",
                endpoint=ResolvedProxyEndpoint("headers-proxy", "http", "127.0.0.1", urlsplit(base_url).port or 80),
            )
            if routed
            else None
        )

        async def resolve(*_args, **_kwargs):
            return route

        monkeypatch.setattr(ProxyService, "_resolve_upstream_route_for_account", resolve)
        response = await asyncio.wait_for(async_client.post("/v1/warmup", json={"mode": "force"}), 2)
        assert response.status_code == 200
        assert response.json()["failed"][0]["error_code"] == "upstream_unavailable"
        await asyncio.wait_for(closed.wait(), 2)
    assert len(hits) == 1 and not native_worker._streams


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["standalone"])
@pytest.mark.parametrize("retained_type", [[], {}], ids=["array", "object"])
async def test_compact_api_reuses_opaque_type_window_after_settlement(
    async_client,
    monkeypatch: pytest.MonkeyPatch,
    native_worker: SubprocessNativeEgressClient,
    surface: str,
    retained_type: object,
) -> None:
    from sqlalchemy import select

    from app.core.openai.requests import ResponsesCompactRequest, ResponsesRequest
    from app.db.models import ApiKeyLimit, ApiKeyUsageReservation, RequestLog
    from app.db.session import SessionLocal
    from app.modules.api_keys.repository import ApiKeysRepository
    from app.modules.api_keys.service import ApiKeysService, ApiKeyUsageReservationData
    from app.modules.proxy.api_key_usage import estimate_api_key_request_usage
    from app.modules.proxy.http_bridge_forwarding import HTTPBridgeForwardContext, build_owner_forward_headers
    from tests.integration.compact_test_helpers import _make_auth_json

    auth = _make_auth_json("opaque-native", "opaque-native@example.com")
    imported = await async_client.post(
        "/api/accounts/import", files={"auth_json": ("auth.json", json.dumps(auth), "application/json")}
    )
    assert imported.status_code == 200
    assert (await async_client.put("/api/settings", json={"apiKeyAuthEnabled": True})).status_code == 200
    created = await async_client.post(
        "/api/api-keys/",
        json={
            "name": "opaque-native-key",
            "limits": [{"limitType": "total_tokens", "limitWindow": "weekly", "maxValue": 100_000}],
        },
    )
    assert created.status_code == 200
    key = created.json()
    settings = proxy_module.get_settings()
    monkeypatch.setattr(proxy_module, "discover_native_egress_client", lambda: native_worker)
    output = [
        {"type": retained_type, "opaque": "retained"},
        {"type": "compaction", "id": "cmp_native_opaque", "encrypted_content": "opaque-capsule", "status": "completed"},
    ]
    reply = {
        "type": "response.completed",
        "response": {
            "id": "opaque-native",
            "object": "response",
            "output": output,
            "usage": {"input_tokens": 1000, "output_tokens": 20, "total_tokens": 1020},
        },
    }
    hits = []

    async def handler(_reader, writer, _head, body):
        hits.append(json.loads(body))
        await _start_chunked_response(writer)
        await _write_chunk(writer, ("data: " + json.dumps(reply) + "\n\n").encode())
        await _finish_chunks(writer)

    compact = ResponsesCompactRequest.model_validate(
        {"model": "gpt-5.4", "instructions": "policy", "input": [{"role": "user", "content": "history"}]}
    )
    headers = {"authorization": "Bearer " + key["key"], "session_id": "opaque-native-session"}
    wire_payload = compact.to_payload()
    path = "/backend-api/codex/responses/compact"
    if surface != "standalone":
        forwarded = ResponsesRequest.model_validate(
            {**wire_payload, "input": [*wire_payload["input"], {"type": "compaction_trigger"}], "stream": True}
        )
        wire_payload = forwarded.model_dump_for_forwarding()
        path = "/backend-api/codex/responses"
        if surface == "bridge":
            async with SessionLocal() as session:
                reservation = await ApiKeysService(ApiKeysRepository(session)).enforce_limits_for_request(
                    key["id"],
                    request_model=compact.model,
                    request_service_tier=None,
                    request_usage_budget=estimate_api_key_request_usage(compact),
                )
                assert reservation is not None
            context = HTTPBridgeForwardContext(
                origin_instance="opaque-origin",
                target_instance=settings.http_responses_session_bridge_instance_id,
                codex_session_affinity=True,
                downstream_turn_state=None,
                reservation=ApiKeyUsageReservationData(
                    reservation_id=reservation.reservation_id, key_id=key["id"], model=compact.model
                ),
            )
            headers = build_owner_forward_headers(headers=headers, payload=forwarded, context=context)
            path = "/internal/bridge/responses"
    async with _serve_http(handler) as base_url:
        monkeypatch.setattr(settings, "upstream_base_url", base_url)
        first = await asyncio.wait_for(async_client.post(path, headers=headers, json=wire_payload), 5)
        assert first.status_code == 200 and first.json()["output"] == output
        wire_payload["input"] = first.json()["output"]
        response = await asyncio.wait_for(async_client.post(path, headers=headers, json=wire_payload), 5)
    assert response.status_code == 200
    if surface == "standalone":
        assert response.json()["output"] == output
    else:
        events = [
            json.loads(line[5:])
            for line in response.text.splitlines()
            if line.startswith("data:") and line[5:].strip() != "[DONE]"
        ]
        terminal = [event for event in events if event.get("type") == "response.completed"]
        assert len(terminal) == 1 and terminal[0]["response"]["output"] == output
        added = [event for event in events if event.get("type") == "response.output_item.added"]
        done = [event for event in events if event.get("type") == "response.output_item.done"]
        assert [event["item"] for event in added] == [output[0], {**output[1], "status": "in_progress"}]
        assert [event["item"] for event in done] == output
        assert [event["output_index"] for event in added] == [0, 1]
    assert len(hits) == 2
    assert hits[1]["input"] == [*output, {"type": "compaction_trigger"}]
    async with SessionLocal() as session:
        reservations = (
            (
                await session.execute(
                    select(ApiKeyUsageReservation).where(ApiKeyUsageReservation.api_key_id == key["id"])
                )
            )
            .scalars()
            .all()
        )
        assert len(reservations) == 2 and all(row.status == "finalized" for row in reservations)
        limit = (await session.execute(select(ApiKeyLimit).where(ApiKeyLimit.api_key_id == key["id"]))).scalar_one()
        assert limit.current_value == 2040
        logs = (
            (await session.execute(select(RequestLog).where(RequestLog.session_id == "opaque-native-session")))
            .scalars()
            .all()
        )
        assert len(logs) == 2
        assert all(
            log.request_kind == "compaction" and log.input_tokens == 1000 and log.output_tokens == 20 for log in logs
        )
    assert not native_worker._streams


@asynccontextmanager
async def _serve_socks_route(base_url: str) -> AsyncIterator[ResolvedUpstreamRoute]:
    """Real local SOCKS5 relay with owned connections and joined pump tasks."""
    tasks: set[asyncio.Task] = set()
    target = urlsplit(base_url)

    async def dispatch(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        upstream_writer = None
        pumps = []
        try:
            version, count = await reader.readexactly(2)
            methods = await reader.readexactly(count)
            assert version == 5 and 0 in methods
            writer.write(b"\x05\x00")
            await writer.drain()
            version, command, reserved, kind = await reader.readexactly(4)
            assert (version, command, reserved) == (5, 1, 0)
            if kind == 1:
                host = socket.inet_ntop(socket.AF_INET, await reader.readexactly(4))
            elif kind == 3:
                size = (await reader.readexactly(1))[0]
                host = (await reader.readexactly(size)).decode()
            else:
                raise AssertionError("unexpected local SOCKS address type")
            port = int.from_bytes(await reader.readexactly(2), "big")
            assert host == "127.0.0.1" and port == target.port
            upstream_reader, upstream_writer = await asyncio.open_connection(host, port)
            writer.write(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")
            await writer.drain()

            async def pump(source, destination):
                while data := await source.read(65536):
                    destination.write(data)
                    await destination.drain()

            pumps = [
                asyncio.create_task(pump(reader, upstream_writer)),
                asyncio.create_task(pump(upstream_reader, writer)),
            ]
            await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            for child in pumps:
                child.cancel()
            if pumps:
                await asyncio.gather(*pumps, return_exceptions=True)
            for connection in (writer, upstream_writer):
                if connection is not None:
                    connection.close()
                    with contextlib.suppress(ConnectionError):
                        await connection.wait_closed()
            tasks.discard(task)

    server = await asyncio.start_server(dispatch, "127.0.0.1", 0)
    try:
        yield ResolvedUpstreamRoute(
            mode="account_bound",
            pool_id="json-fallback",
            endpoint=ResolvedProxyEndpoint("json-fallback", "socks5", "127.0.0.1", server.sockets[0].getsockname()[1]),
        )
    finally:
        server.close()
        await server.wait_closed()
        for task in tuple(tasks):
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancellation", ["edge", "level", "deadline"])
async def test_socks_compact_header_cancellation_joins_session_close(async_client, monkeypatch, cancellation):
    from unittest.mock import AsyncMock

    import app.core.clients.codex as codex_module
    from app.modules.proxy.service import ProxyService
    from tests.integration.compact_test_helpers import _make_auth_json

    auth = _make_auth_json("socks-header", "socks-header@example.com")
    assert (
        await async_client.post(
            "/api/accounts/import", files={"auth_json": ("auth.json", json.dumps(auth), "application/json")}
        )
    ).status_code == 200
    monkeypatch.setattr("app.modules.proxy.work_admission.ADMISSION_WAIT_TIMEOUT_SECONDS", 0.05)
    assert (
        await async_client.put(
            "/api/settings",
            json={
                "warmupModel": "gpt-5.4-nano",
                "upstreamConnectTimeoutSeconds": 0.1,
                "compactRequestBudgetSeconds": 0.2 if cancellation == "deadline" else 5.0,
            },
        )
    ).status_code == 200
    monkeypatch.setattr(proxy_module, "discover_native_egress_client", lambda: None)
    monkeypatch.setattr(codex_module, "discover_native_egress_client", lambda: None)
    sessions, scopes, core_tasks = [], [], []
    received, closing, resume, disconnected = (asyncio.Event() for _ in range(4))
    init_original, close_original = aiohttp.ClientSession.__init__, aiohttp.ClientSession.close
    core_original = proxy_module.compact_responses
    request_original = aiohttp.ClientSession._request
    request_cancelled = asyncio.Event()

    def session_init(self, *args, **kwargs):
        init_original(self, *args, **kwargs)
        if isinstance(kwargs.get("connector"), codex_module.ProxyConnector):
            sessions.append(self)

    async def session_close(self):
        if self in sessions:
            closing.set()
            await resume.wait()
        await close_original(self)

    async def observe_request(self, *args, **kwargs):
        try:
            return await request_original(self, *args, **kwargs)
        except (asyncio.CancelledError, TimeoutError):
            if self in sessions:
                request_cancelled.set()
            raise

    async def tracked_core(*args, **kwargs):
        core_tasks.append(asyncio.current_task())
        return await core_original(*args, **kwargs)

    async def fresh(self, account, **_kwargs):
        return account

    monkeypatch.setattr(aiohttp.ClientSession, "__init__", session_init)
    monkeypatch.setattr(aiohttp.ClientSession, "close", session_close)
    monkeypatch.setattr(aiohttp.ClientSession, "_request", observe_request)
    monkeypatch.setattr("app.modules.proxy.service.core_compact_responses", tracked_core)
    monkeypatch.setattr(ProxyService, "_ensure_fresh_with_budget", fresh)
    monkeypatch.setattr(ProxyService, "_handle_proxy_error", AsyncMock())

    async def handler(reader, _writer, _head, _body):
        received.set()
        await reader.read()
        disconnected.set()

    async def submit():
        with anyio.CancelScope() as scope:
            scopes.append(scope)
            return await async_client.post("/v1/warmup", json={"mode": "force"})

    settings = proxy_module.get_settings()
    async with _serve_http(handler) as base_url, _serve_socks_route(base_url) as route:
        monkeypatch.setattr(settings, "upstream_base_url", base_url)

        async def resolve(*_args, **_kwargs):
            return route

        monkeypatch.setattr(ProxyService, "_resolve_upstream_route_for_account", resolve)
        task = asyncio.create_task(submit())
        waiter = asyncio.create_task(closing.wait())
        try:
            await asyncio.wait_for(received.wait(), 2)
            assert sessions and core_tasks
            if cancellation == "edge":
                task.cancel()
            elif cancellation == "level":
                scopes[0].cancel()
            done, _ = await asyncio.wait([task, waiter], timeout=2, return_when=asyncio.FIRST_COMPLETED)
            assert done
            if not closing.is_set():
                assert all(session.closed for session in sessions), "cancelled SOCKS session has no close owner"
            else:
                assert request_cancelled.is_set(), "request cancellation/timeout must precede ownership close"
                assert not task.done(), "request must join its suspended session close"
            resume.set()
            with contextlib.suppress(asyncio.CancelledError):
                response = await asyncio.wait_for(task, 2)
                if cancellation == "deadline":
                    assert response.status_code == 200 and response.json()["failed"]
            assert all(session.closed and session.connector is None for session in sessions)
            await asyncio.wait_for(disconnected.wait(), 2)
        finally:
            resume.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)
            for session in sessions:
                if not session.closed:
                    await close_original(session)
