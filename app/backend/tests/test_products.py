"""GET /api/products/{id} -- the catalog contract the frontend depends on."""

from __future__ import annotations

import httpx
from fastapi import FastAPI


async def test_returns_product_dimensions_and_every_sku(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/products/aurora-tee")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "aurora-tee"
    assert body["currency"] == "USD"
    assert [dimension["key"] for dimension in body["option_dimensions"]] == ["colour", "size"]
    assert len(body["skus"]) == 7


async def test_each_sku_is_fully_described(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/products/aurora-tee")).json()

    for sku in body["skus"]:
        assert sku["id"], "every SKU needs its own id"
        assert sku["price_minor"] > 0
        assert sku["image_url"].startswith("/images/")
        assert set(sku["options"]) == {"colour", "size"}, "each SKU keeps a value for every dimension"
        assert sku["in_stock"] is (sku["available_quantity"] > 0)


async def test_seed_offers_an_out_of_stock_sku_and_missing_combinations(
    client: httpx.AsyncClient,
) -> None:
    body = (await client.get("/api/products/aurora-tee")).json()

    by_id = {sku["id"]: sku for sku in body["skus"]}
    assert by_id["TEE-SND-S"]["available_quantity"] == 0
    assert by_id["TEE-SND-S"]["in_stock"] is False

    # The frontend derives "impossible combination" from the absence of a SKU, so the
    # catalog has to expose a gap rather than a SKU flagged as unusable.
    combinations = {(sku["options"]["colour"], sku["options"]["size"]) for sku in body["skus"]}
    per_dimension = [len(dimension["values"]) for dimension in body["option_dimensions"]]
    theoretical = per_dimension[0] * per_dimension[1]

    assert len(combinations) == 7
    assert theoretical - len(combinations) == 2
    assert ("black", "l") not in combinations
    assert ("sage", "s") not in combinations


async def test_availability_reflects_live_reservations(client: httpx.AsyncClient, add_to_cart) -> None:
    """The catalog reports current stock, not seed stock: the UI gates on this number."""
    assert (await add_to_cart("TEE-BLK-S", 3, "reserve-3")).status_code == 201

    body = (await client.get("/api/products/aurora-tee")).json()
    by_id = {sku["id"]: sku for sku in body["skus"]}

    assert by_id["TEE-BLK-S"]["available_quantity"] == 1
    assert by_id["TEE-BLK-M"]["available_quantity"] == 2, "other SKUs are untouched"


async def test_unknown_product_is_a_structured_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/products/nope")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "PRODUCT_NOT_FOUND"
    assert error["details"] == {"product_id": "nope"}
    assert error["request_id"], "every error carries a correlation id"
    assert response.headers["X-Request-ID"] == error["request_id"]


async def test_unknown_route_uses_the_same_envelope(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_health_endpoint(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_unexpected_failure_becomes_a_structured_500(app: FastAPI, monkeypatch) -> None:
    """An unhandled exception must not leak internals or a stack trace."""

    def explode(product_id: str) -> None:
        raise RuntimeError("internal detail that must not reach the client")

    monkeypatch.setattr(app.state.store, "get_product", explode)

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/products/aurora-tee")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "internal detail" not in response.text
