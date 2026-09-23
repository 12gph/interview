"""POST /api/cart/items and GET /api/cart -- success and validation paths."""

from __future__ import annotations

import httpx
import pytest


async def test_adds_a_line_and_reports_updated_availability(client: httpx.AsyncClient, add_to_cart) -> None:
    response = await add_to_cart("TEE-BLK-M", 2, "add-1")

    assert response.status_code == 201
    body = response.json()
    line = body["cart"]["items"][0]

    assert line["sku_id"] == "TEE-BLK-M"
    assert line["quantity"] == 2
    assert line["unit_price_minor"] == 4900
    assert line["line_total_minor"] == 9800
    assert "Black" in line["name"] and "M" in line["name"]
    assert body["cart"]["total_item_count"] == 2
    assert body["cart"]["subtotal_minor"] == 9800
    # Inlined so the client can correct its own stock figure without a second call.
    assert body["sku_availability"] == {"sku_id": "TEE-BLK-M", "available_quantity": 0}
    assert "Idempotency-Replayed" not in response.headers


async def test_adding_the_same_sku_twice_accumulates_into_one_line(
    client: httpx.AsyncClient, add_to_cart
) -> None:
    await add_to_cart("TEE-BLK-S", 1, "acc-1")
    second = await add_to_cart("TEE-BLK-S", 2, "acc-2")

    cart = second.json()["cart"]
    assert len(cart["items"]) == 1, "the cart keeps one line per SKU"
    assert cart["items"][0]["quantity"] == 3
    assert cart["total_item_count"] == 3


async def test_adds_multiple_skus_and_totals_them(client: httpx.AsyncClient, add_to_cart) -> None:
    await add_to_cart("TEE-BLK-S", 2, "multi-1")
    await add_to_cart("TEE-SND-M", 3, "multi-2")

    cart = (await client.get("/api/cart")).json()
    assert [line["sku_id"] for line in cart["items"]] == ["TEE-BLK-S", "TEE-SND-M"]
    assert cart["total_item_count"] == 5, "counts items, not lines"
    assert cart["subtotal_minor"] == 2 * 4900 + 3 * 5300


async def test_empty_cart_is_a_valid_response(client: httpx.AsyncClient) -> None:
    cart = (await client.get("/api/cart")).json()

    assert cart["items"] == []
    assert cart["total_item_count"] == 0
    assert cart["subtotal_minor"] == 0


@pytest.mark.parametrize("quantity", [0, -1, 1.5, 101, "many", None])
async def test_invalid_quantity_is_rejected_with_a_structured_400(
    client: httpx.AsyncClient, add_to_cart, quantity: object
) -> None:
    response = await add_to_cart("TEE-BLK-M", quantity, f"bad-{quantity}")

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["fields"][0]["field"] == "quantity"


async def test_missing_idempotency_key_is_rejected(client: httpx.AsyncClient, add_to_cart) -> None:
    response = await add_to_cart("TEE-BLK-M", 1, omit_key_header=True)

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["field"] == "Idempotency-Key"


async def test_overlong_idempotency_key_is_rejected(client: httpx.AsyncClient, add_to_cart) -> None:
    response = await add_to_cart("TEE-BLK-M", 1, "x" * 129)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_unknown_sku_is_a_structured_404(client: httpx.AsyncClient, add_to_cart) -> None:
    response = await add_to_cart("TEE-NOPE-X", 1, "unknown-1")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "SKU_NOT_FOUND"
    assert error["details"] == {"sku_id": "TEE-NOPE-X"}


async def test_insufficient_stock_reports_the_authoritative_availability(
    client: httpx.AsyncClient, add_to_cart
) -> None:
    response = await add_to_cart("TEE-BLK-M", 3, "over-1")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INSUFFICIENT_STOCK"
    assert error["details"] == {"sku_id": "TEE-BLK-M", "requested": 3, "available": 2}


async def test_out_of_stock_sku_cannot_be_added(client: httpx.AsyncClient, add_to_cart) -> None:
    response = await add_to_cart("TEE-SND-S", 1, "oos-1")

    assert response.status_code == 409
    assert response.json()["error"]["details"]["available"] == 0


async def test_client_supplied_price_or_stock_is_rejected_rather_than_ignored(
    client: httpx.AsyncClient,
) -> None:
    """Enforcement of "never trust price or stock sent by the client".

    Rejecting is a stronger guarantee than ignoring: the attempt becomes visible to the
    client instead of leaving it to guess whether the field took effect.
    """
    response = await client.post(
        "/api/cart/items",
        json={"sku_id": "TEE-BLK-M", "quantity": 1, "price_minor": 1, "available_quantity": 999},
        headers={"Idempotency-Key": "forge-1"},
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    reported = {field["field"] for field in error["details"]["fields"]}
    assert {"price_minor", "available_quantity"} <= reported

    # ...and nothing was reserved as a side effect.
    assert (await client.get("/api/cart")).json()["items"] == []


async def test_unparseable_body_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/cart/items",
        content=b"not json at all",
        headers={"Idempotency-Key": "junk-1", "Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_preflight_advertises_the_idempotency_key_header(client: httpx.AsyncClient) -> None:
    """Guards the classic failure mode: works under curl, blocked in the browser."""
    response = await client.options(
        "/api/cart/items",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Idempotency-Key",
        },
    )

    assert response.status_code == 200
    assert "idempotency-key" in response.headers["access-control-allow-headers"].lower()
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
