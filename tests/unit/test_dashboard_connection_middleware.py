from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.modules.read_snapshots.connection_middleware import DashboardConnectionMiddleware


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,version,tags,close",
    [
        ("/", "1.1", [], True),
        ("/assets/app.js", "1.1", [], True),
        ("/api/dashboard/projections", "1.0", ["dashboard"], True),
        ("/api/reports", "2", ["dashboard"], False),
        ("/v1/responses", "1.1", ["proxy"], False),
        ("/backend-api/codex/responses", "1.1", [], False),
        ("/internal/bridge", "1.1", [], False),
        ("/health/ready", "1.1", [], False),
        ("/metrics", "1.1", [], False),
        ("/scim/v2/Users", "1.1", [], False),
        ("/responses", "1.1", ["proxy"], False),
    ],
)
async def test_connection_policy_preserves_inference_streams(path, version, tags, close):
    seen = []
    streaming = False

    async def send(message):
        seen.append(message)

    async def receive():
        return {"type": "http.request", "body": b""}

    async def app(scope, receive, send):
        nonlocal streaming
        scope["route"] = SimpleNamespace(tags=tags)
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"first", "more_body": True})
        assert seen[-1]["body"] == b"first"  # Middleware cannot buffer the stream.
        streaming = True
        await send({"type": "http.response.body", "body": b"last", "more_body": False})

    await DashboardConnectionMiddleware(app)({"type": "http", "path": path, "http_version": version}, receive, send)
    assert streaming
    assert ((b"connection", b"close") in seen[0]["headers"]) is close
    assert b"".join(message.get("body", b"") for message in seen) == b"firstlast"


@pytest.mark.asyncio
async def test_websocket_is_untouched():
    seen = []

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        await send({"type": "websocket.send", "text": "payload"})

    async def send(message):
        seen.append(message)

    async def receive():
        return {"type": "websocket.connect"}

    await DashboardConnectionMiddleware(app)({"type": "websocket", "path": "/v1/responses"}, receive, send)
    assert seen == [{"type": "websocket.accept"}, {"type": "websocket.send", "text": "payload"}]
