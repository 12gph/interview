"""Concurrency: requests competing for the final unit.

These run a real ``asyncio.gather`` on a single event loop. Firing the same requests
sequentially would pass even with no concurrency control whatsoever, so it would be a
test of nothing -- the interleaving is the entire point.

``Store._reserve`` contains a deliberate ``await asyncio.sleep(0)`` standing in for the
database round trip this will become in production. That suspension point is what makes
the race real: without the lock, both tasks read the same ``available`` value and both
proceed. Remove the lock in ``Store.add_to_cart`` and these tests fail -- see the README.
"""

from __future__ import annotations

import asyncio

import httpx
from fastapi import FastAPI


def make_client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )


async def attempt(client: httpx.AsyncClient, sku_id: str, quantity: int, key: str) -> httpx.Response:
    return await client.post(
        "/api/cart/items",
        json={"sku_id": sku_id, "quantity": quantity},
        headers={"Idempotency-Key": key},
    )


async def test_two_requests_for_the_last_unit_produce_exactly_one_winner(app: FastAPI) -> None:
    """``TEE-SGE-M`` is seeded with a single unit on purpose."""
    async with make_client(app) as client:
        responses = await asyncio.gather(
            attempt(client, "TEE-SGE-M", 1, "race-a"),
            attempt(client, "TEE-SGE-M", 1, "race-b"),
        )

    assert sorted(response.status_code for response in responses) == [201, 409]
    assert app.state.store.get_cart().total_item_count == 1


async def test_only_three_of_eight_concurrent_requests_can_win(app: FastAPI) -> None:
    """``TEE-SND-L`` is seeded with three units."""
    async with make_client(app) as client:
        responses = await asyncio.gather(
            *(attempt(client, "TEE-SND-L", 1, f"crowd-{index}") for index in range(8))
        )

    statuses = [response.status_code for response in responses]
    assert statuses.count(201) == 3
    assert statuses.count(409) == 5
    assert app.state.store.get_cart().total_item_count == 3


async def test_bulk_requests_cannot_oversell(app: FastAPI) -> None:
    """``TEE-SGE-L`` holds five units and each request wants three, so exactly one fits."""
    async with make_client(app) as client:
        responses = await asyncio.gather(
            *(attempt(client, "TEE-SGE-L", 3, f"bulk-{index}") for index in range(10))
        )

    statuses = [response.status_code for response in responses]
    assert statuses.count(201) == 1
    assert statuses.count(409) == 9
    assert app.state.store.get_cart().total_item_count == 3


async def test_concurrent_requests_with_the_same_key_apply_once(app: FastAPI) -> None:
    """The duplication the Idempotency-Key exists to prevent, under real concurrency.

    Without the lock both tasks would miss the lookup and both would reserve stock -- one
    cart line added twice by a single logical request.
    """
    async with make_client(app) as client:
        responses = await asyncio.gather(
            attempt(client, "TEE-BLK-S", 2, "one-key"),
            attempt(client, "TEE-BLK-S", 2, "one-key"),
        )

    assert {response.status_code for response in responses} == {201}
    assert responses[0].json() == responses[1].json()
    assert app.state.store.get_cart().total_item_count == 2
