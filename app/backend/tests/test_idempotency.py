"""Idempotent add-to-cart.

Mirrors the rule from Task A: a request that was *processed* -- whether it succeeded or
was rejected on business grounds -- is never processed a second time under the same key.
"""

from __future__ import annotations

import httpx


async def test_replay_returns_the_stored_response_and_does_not_add_twice(
    client: httpx.AsyncClient, add_to_cart
) -> None:
    first = await add_to_cart("TEE-BLK-M", 1, "replay-1")
    replay = await add_to_cart("TEE-BLK-M", 1, "replay-1")

    assert first.status_code == replay.status_code == 201
    assert replay.json() == first.json(), "the stored response, byte for byte"
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert "Idempotency-Replayed" not in first.headers

    assert (await client.get("/api/cart")).json()["total_item_count"] == 1


async def test_replay_does_not_reserve_stock_twice(client: httpx.AsyncClient, add_to_cart) -> None:
    await add_to_cart("TEE-BLK-S", 2, "stock-1")
    await add_to_cart("TEE-BLK-S", 2, "stock-1")

    by_id = {sku["id"]: sku for sku in (await client.get("/api/products/aurora-tee")).json()["skus"]}
    assert by_id["TEE-BLK-S"]["available_quantity"] == 2, "4 seeded minus 2 reserved, exactly once"


async def test_same_key_with_a_different_body_is_a_conflict(
    client: httpx.AsyncClient, add_to_cart
) -> None:
    assert (await add_to_cart("TEE-BLK-S", 1, "shared")).status_code == 201

    response = await add_to_cart("TEE-BLK-S", 2, "shared")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    assert error["details"]["idempotency_key"] == "shared"

    assert (await client.get("/api/cart")).json()["total_item_count"] == 1


async def test_different_keys_apply_independently(client: httpx.AsyncClient, add_to_cart) -> None:
    await add_to_cart("TEE-BLK-S", 1, "key-a")
    await add_to_cart("TEE-BLK-S", 1, "key-b")

    assert (await client.get("/api/cart")).json()["total_item_count"] == 2


async def test_a_rejected_attempt_is_still_processed_for_idempotency(
    client: httpx.AsyncClient, add_to_cart
) -> None:
    """Task A's rule, over HTTP.

    The first attempt is rejected for insufficient stock. Replaying the key must
    reproduce that exact response rather than re-running the decision. Both bodies
    matching byte for byte -- including the original request id -- is what demonstrates
    that no second execution took place.
    """
    rejected = await add_to_cart("TEE-BLK-M", 5, "reject-once")
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "INSUFFICIENT_STOCK"

    replay = await add_to_cart("TEE-BLK-M", 5, "reject-once")

    assert replay.status_code == 409
    assert replay.json() == rejected.json()
    assert replay.headers["Idempotency-Replayed"] == "true"


async def test_a_malformed_request_does_not_consume_the_key(
    client: httpx.AsyncClient, add_to_cart
) -> None:
    """Syntactic validation runs before the store, so a bad body leaves the key unused.

    Same ordering as Task A, where a malformed line does not occupy an event id.
    """
    bad = await add_to_cart("TEE-BLK-M", 0, "careful")
    assert bad.status_code == 400

    good = await add_to_cart("TEE-BLK-M", 1, "careful")

    assert good.status_code == 201
    assert (await client.get("/api/cart")).json()["total_item_count"] == 1
