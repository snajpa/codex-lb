"""Do not retain dashboard HTTP pools across an atomic backend generation switch."""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_NON_DASHBOARD_PREFIXES = ("/v1", "/backend-api", "/internal", "/health", "/metrics", "/scim")


class DashboardConnectionMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        root = scope.get("root_path", "")
        if root and path.startswith(root + "/"):
            path = path[len(root) :]
        excluded = any(path == prefix or path.startswith(prefix + "/") for prefix in _NON_DASHBOARD_PREFIXES)
        if scope["type"] != "http" or scope.get("http_version", "1.1") not in ("1.0", "1.1") or excluded:
            await self.app(scope, receive, send)
            return

        async def send_dashboard(message: Message) -> None:
            route = scope.get("route")
            if message["type"] == "http.response.start" and "proxy" not in getattr(route, "tags", ()):
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() not in (b"connection", b"keep-alive")
                ]
                message = {**message, "headers": [*headers, (b"connection", b"close")]}
            await send(message)

        # Streaming bodies are neither buffered nor cancelled. Only the HTTP
        # connection after a dashboard response completes is retired.
        await self.app(scope, receive, send_dashboard)
