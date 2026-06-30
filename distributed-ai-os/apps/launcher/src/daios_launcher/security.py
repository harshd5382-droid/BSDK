"""Launcher API token authentication."""

from __future__ import annotations

import ipaddress

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host in {"localhost", "::1"}


class LauncherTokenMiddleware(BaseHTTPMiddleware):
    """Require ``X-DAIOS-Token`` for non-loopback requests to launcher API."""

    def __init__(self, app, token: str | None) -> None:
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next):
        if not self.token:
            return await call_next(request)
        path = request.url.path
        if not path.startswith("/api/launcher"):
            return await call_next(request)
        client = request.client.host if request.client else None
        if _is_loopback(client):
            return await call_next(request)
        supplied = request.headers.get("x-daios-token", "")
        if supplied != self.token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing cluster token"},
            )
        return await call_next(request)
