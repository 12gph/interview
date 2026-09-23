"""In-memory state and the concurrency control that protects it.

Design rule: every change to stock, cart contents or idempotency records happens
inside this module while holding ``self._lock``. Routers never mutate state
directly, so the question "can this oversell?" is answered by reading one file.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import Any

from .config import MAX_CART_LINES
from .errors import (
    ApiError,
    IdempotencyKeyConflict,
    InsufficientStock,
    ProductNotFound,
    SkuNotFound,
    ValidationError,
)
from .models import (
    AddCartItemResponse,
    Cart,
    CartLine,
    OptionDimension,
    OptionValue,
    Product,
    Sku,
    SkuAvailability,
)
from .seed import SeedProduct

CART_ID = "cart-1"


@dataclass
class SkuState:
    """Mutable counterpart of a seed SKU.

    Stock is held as two counters (``stock`` and ``reserved``) instead of one
    decremented number. ``available`` is derived, which keeps the original quantity
    auditable: "we had 4, and 3 of them are sitting in carts" stays answerable,
    whereas a single decremented field loses that distinction forever.
    """

    id: str
    options: dict[str, str]
    price_minor: int
    stock: int
    image_url: str
    reserved: int = 0

    @property
    def available(self) -> int:
        return self.stock - self.reserved


@dataclass
class IdempotencyRecord:
    """A stored response, keyed by the client-supplied Idempotency-Key."""

    fingerprint: str
    status_code: int
    body: dict[str, Any]


@dataclass
class AddOutcome:
    status_code: int
    body: dict[str, Any]
    replayed: bool


def fingerprint_request(sku_id: str, quantity: int) -> str:
    """Identify the *request*, so the same key used with a different body is detectable."""
    return hashlib.sha256(f"{sku_id}\x1f{quantity}".encode("utf-8")).hexdigest()


class Store:
    """Single source of truth for catalog, cart and idempotency records."""

    def __init__(self, seed: SeedProduct) -> None:
        self._seed = seed
        self._lock = asyncio.Lock()
        self._skus: dict[str, SkuState] = {
            item.id: SkuState(
                id=item.id,
                options=dict(item.options),
                price_minor=item.price_minor,
                stock=item.stock,
                image_url=item.image_url,
            )
            for item in seed.skus
        }
        self._option_labels: dict[str, dict[str, str]] = {
            dimension.key: {value.value: value.label for value in dimension.values}
            for dimension in seed.dimensions
        }
        # sku_id -> quantity. A cart holds at most one line per SKU, so adding an
        # SKU that is already present accumulates instead of duplicating the line.
        self._cart_quantities: dict[str, int] = {}
        self._idempotency: dict[str, IdempotencyRecord] = {}

    # ------------------------------------------------------------------ reads

    def get_product(self, product_id: str) -> Product:
        """Read the catalog.

        No lock is taken: this method contains no ``await``, so in asyncio's
        single-threaded model it cannot be interleaved by another task. Adding a
        lock here would suggest a hazard that does not exist.
        """
        if product_id != self._seed.id:
            raise ProductNotFound(product_id)

        return Product(
            id=self._seed.id,
            name=self._seed.name,
            description=self._seed.description,
            currency=self._seed.currency,
            hero_image_url=self._seed.hero_image_url,
            option_dimensions=[
                OptionDimension(
                    key=dimension.key,
                    label=dimension.label,
                    values=[
                        OptionValue(value=v.value, label=v.label, swatch=v.swatch)
                        for v in dimension.values
                    ],
                )
                for dimension in self._seed.dimensions
            ],
            # Sorted by id so the payload is stable between calls -- the client
            # diffs nothing, but tests and humans both benefit from determinism.
            skus=[self._public_sku(self._skus[key]) for key in sorted(self._skus)],
        )

    def get_cart(self) -> Cart:
        return self._build_cart()

    # ------------------------------------------------------------------ write

    async def add_to_cart(
        self,
        *,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
        request_id: str,
    ) -> AddOutcome:
        """Reserve stock and record the line, exactly once per Idempotency-Key.

        The whole "look up the key -> apply the change -> store the response"
        sequence runs inside one critical section. Splitting it would let two
        concurrent requests carrying the same key both miss the lookup and both
        apply the change -- the very duplication the header exists to prevent.
        """
        fingerprint = fingerprint_request(sku_id, quantity)

        async with self._lock:
            record = self._idempotency.get(idempotency_key)
            if record is not None:
                if record.fingerprint != fingerprint:
                    # Reporting the clash beats returning the stored response: a
                    # client reusing a key for a different body has a bug, and
                    # hiding it would surface later as a phantom cart line.
                    raise IdempotencyKeyConflict(idempotency_key)
                return AddOutcome(record.status_code, record.body, replayed=True)

            try:
                body = await self._reserve(sku_id, quantity)
            except ApiError as exc:
                # A rejected attempt still counts as *processed*: replaying this key
                # must reproduce the rejection rather than get a second chance to
                # succeed. This mirrors Task A's rule that a business-rejected event
                # is nevertheless considered handled for idempotency.
                self._idempotency[idempotency_key] = IdempotencyRecord(
                    fingerprint, exc.status_code, exc.to_payload(request_id)
                )
                raise

            self._idempotency[idempotency_key] = IdempotencyRecord(fingerprint, 201, body)
            return AddOutcome(status_code=201, body=body, replayed=False)

    async def _reserve(self, sku_id: str, quantity: int) -> dict[str, Any]:
        """Validate against authoritative state and apply the reservation.

        Caller must hold the lock.

        The ``sleep(0)`` stands in for the database round trip this will become in
        production, and it sits deliberately between *reading* ``available`` and acting
        on it -- the exact window a real round trip would open. That placement is what
        makes the stock-race tests meaningful: put the suspension point before the read
        instead and the race disappears, so the tests would pass with the lock removed
        and prove nothing. Remove the lock and they fail -- see the README.
        """
        sku = self._skus.get(sku_id)
        if sku is None:
            raise SkuNotFound(sku_id)

        available = sku.available
        await asyncio.sleep(0)
        if quantity > available:
            raise InsufficientStock(sku_id, quantity, available)

        is_new_line = sku_id not in self._cart_quantities
        if is_new_line and len(self._cart_quantities) >= MAX_CART_LINES:
            raise ValidationError(
                "The cart cannot hold more distinct SKUs.",
                details={"max_lines": MAX_CART_LINES},
            )

        sku.reserved += quantity
        self._cart_quantities[sku_id] = self._cart_quantities.get(sku_id, 0) + quantity

        return AddCartItemResponse(
            cart=self._build_cart(),
            sku_availability=SkuAvailability(sku_id=sku.id, available_quantity=sku.available),
        ).model_dump()

    # ----------------------------------------------------------------- helpers

    def _build_cart(self) -> Cart:
        lines = [
            self._cart_line(self._skus[sku_id], self._cart_quantities[sku_id])
            for sku_id in sorted(self._cart_quantities)
        ]
        return Cart(
            id=CART_ID,
            currency=self._seed.currency,
            items=lines,
            total_item_count=sum(line.quantity for line in lines),
            subtotal_minor=sum(line.line_total_minor for line in lines),
        )

    def _cart_line(self, sku: SkuState, quantity: int) -> CartLine:
        return CartLine(
            sku_id=sku.id,
            quantity=quantity,
            unit_price_minor=sku.price_minor,
            line_total_minor=sku.price_minor * quantity,
            name=f"{self._seed.name} — {self._describe(sku.options)}",
            image_url=sku.image_url,
            options=dict(sku.options),
        )

    def _describe(self, options: dict[str, str]) -> str:
        parts = []
        for dimension in self._seed.dimensions:
            value = options.get(dimension.key)
            if value is None:
                continue
            parts.append(self._option_labels[dimension.key].get(value, value))
        return " / ".join(parts)

    def _public_sku(self, sku: SkuState) -> Sku:
        return Sku(
            id=sku.id,
            options=dict(sku.options),
            price_minor=sku.price_minor,
            currency=self._seed.currency,
            available_quantity=sku.available,
            in_stock=sku.available > 0,
            image_url=sku.image_url,
        )
