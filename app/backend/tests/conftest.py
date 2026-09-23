"""Shared fixtures.

Every test gets a fresh `Store`. That matters more than usual here: the cart and the
stock counters *are* the system under test, so state leaking between tests would
quietly turn assertions about stock into assertions about test execution order.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest
from fastapi import FastAPI

from backend.main import create_app
from backend.seed import SEED_PRODUCT
from backend.store import Store

BASE_URL = "http://testserver"

AddToCart = Callable[..., Awaitable[httpx.Response]]


@pytest.fixture
def store() -> Store:
    return Store(SEED_PRODUCT)


@pytest.fixture
def app(store: Store) -> FastAPI:
    return create_app(store)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """An HTTP client bound straight to the ASGI app -- no socket, no server."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as http_client:
        yield http_client


@pytest.fixture
def add_to_cart(client: httpx.AsyncClient) -> AddToCart:
    """POST /api/cart/items with the Idempotency-Key header filled in.

    The header is required on every call, so spelling it out in each test would be
    noise; `headers=` can still be passed explicitly by tests that need to omit or
    override it.
    """

    async def _add(
        sku_id: str,
        quantity: int,
        key: str = "test-key",
        *,
        headers: dict[str, str] | None = None,
        omit_key_header: bool = False,
    ) -> httpx.Response:
        merged = {"Idempotency-Key": key}
        if headers:
            merged.update(headers)
        if omit_key_header:
            merged.pop("Idempotency-Key", None)
        return await client.post(
            "/api/cart/items",
            json={"sku_id": sku_id, "quantity": quantity},
            headers=merged,
        )

    return _add
