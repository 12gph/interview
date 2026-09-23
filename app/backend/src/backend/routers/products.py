"""Catalog endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from ..models import Product
from ..store import Store


def build_router(store: Store) -> APIRouter:
    """Build the catalog router against a specific store instance.

    The store is passed in rather than imported from a module global so tests can
    hand in a fresh one per test.
    """
    router = APIRouter(tags=["catalog"])

    @router.get(
        "/products/{product_id}",
        response_model=Product,
        summary="Product, option dimensions and every SKU",
        responses={404: {"description": "PRODUCT_NOT_FOUND"}},
    )
    async def get_product(product_id: str) -> Product:
        """Return everything the PDP needs to resolve variants locally.

        One round trip on purpose: if the client had to fetch SKUs per selection it
        would have to re-render while requests were in flight, which is how stale
        UI gets introduced.
        """
        return store.get_product(product_id)

    return router
