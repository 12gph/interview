"""Application factory and ASGI entry point.

Run it with::

    uv run uvicorn backend.main:app --reload --port 8000

See the root README for the full setup instructions.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from . import config
from .errors import register_exception_handlers
from .middleware import REQUEST_ID_HEADER, REPLAYED_HEADER, RequestIdMiddleware
from .models import HealthResponse
from .routers import cart as cart_routes
from .routers import products as product_routes
from .seed import SEED_PRODUCT
from .store import Store


def create_app(store: Store | None = None) -> FastAPI:
    """Build the FastAPI application.

    ``store`` is injectable so each test gets isolated state without reaching into
    module globals or restarting the process.
    """
    app = FastAPI(
        title=config.APP_NAME,
        version=config.APP_VERSION,
        summary="Catalog and cart endpoints behind a variant product detail page.",
    )

    resolved_store = store or Store(SEED_PRODUCT)
    # Kept on app state as well: useful from a REPL, and it lets a test assert on
    # store internals without holding its own reference.
    app.state.store = resolved_store

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins(),
        allow_methods=["GET", "POST", "OPTIONS"],
        # A custom request header must be listed explicitly, otherwise the browser's
        # preflight fails and add-to-cart breaks in the browser while still working
        # under curl. Idempotency-Key lives here for exactly that reason.
        allow_headers=["Content-Type", config.IDEMPOTENCY_KEY_HEADER],
        expose_headers=[REQUEST_ID_HEADER, REPLAYED_HEADER],
    )
    # Added after CORS, so it wraps it and the correlation id is available before
    # anything else runs.
    app.add_middleware(RequestIdMiddleware)

    register_exception_handlers(app)

    # FastAPI advertises a 422 for every endpoint that takes a body, but `errors.py`
    # rewrites validation failures to 400 so that every error shares one envelope. A
    # published schema promising a 422 this service never sends would contradict that on
    # the one surface a reviewer is most likely to read, so the entry is dropped.
    def openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            summary=app.summary,
            routes=app.routes,
        )
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                responses = operation.get("responses")
                if isinstance(responses, dict):
                    responses.pop("422", None)

        app.openapi_schema = schema
        return schema

    app.openapi = openapi

    app.include_router(product_routes.build_router(resolved_store), prefix="/api")
    app.include_router(cart_routes.build_router(resolved_store), prefix="/api")

    @app.get(
        "/api/health",
        response_model=HealthResponse,
        tags=["ops"],
        summary="Liveness probe, used by the single-command dev launcher",
    )
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", version=config.APP_VERSION)

    return app


app = create_app()
