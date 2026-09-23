"""Request-scoped context.

Implemented as raw ASGI rather than ``BaseHTTPMiddleware`` for two reasons: the
error handlers must be able to recover the id even for responses the inner app
never produced, and raw middleware avoids the extra task ``BaseHTTPMiddleware``
wraps around every request -- exactly the kind of scheduling subtlety the
stock-race test is sensitive to.
"""

from __future__ import annotations

import uuid

from fastapi import Request
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
REPLAYED_HEADER = "Idempotency-Replayed"


def new_request_id() -> str:
    """Short id, long enough to correlate logs within a session and short enough to read."""
    return uuid.uuid4().hex[:8]


def request_id_of(request: Request) -> str:
    """Return this request's correlation id, minting one if it is not attached yet.

    Minting on demand is not laziness: an unhandled exception is turned into a
    response by Starlette's *outermost* middleware, which sits outside our own, so
    by the time the 500 handler runs the id may never have been set.
    """
    state = request.scope.setdefault("state", {})
    if "request_id" not in state:
        state["request_id"] = new_request_id()
    return str(state["request_id"])


class RequestIdMiddleware:
    """Attach a correlation id to the request scope and every response."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = new_request_id()
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        await self._app(scope, receive, send_with_request_id)
