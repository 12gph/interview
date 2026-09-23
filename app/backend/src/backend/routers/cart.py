"""Cart endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from ..config import IDEMPOTENCY_KEY_HEADER, IDEMPOTENCY_KEY_MAX_LENGTH
from ..errors import ValidationError
from ..middleware import REPLAYED_HEADER, request_id_of
from ..models import AddCartItemRequest, AddCartItemResponse, Cart
from ..store import Store


def require_idempotency_key(request: Request) -> str:
    """Read and validate the ``Idempotency-Key`` header.

    An absent key is rejected rather than generated server-side. The key is the
    only thing that makes a client retry safe, so a client unable to supply one
    cannot be protected -- and should be told so instead of silently receiving a
    guarantee that does not hold.
    """
    raw = request.headers.get(IDEMPOTENCY_KEY_HEADER)
    if raw is None or raw == "":
        raise ValidationError(
            f"{IDEMPOTENCY_KEY_HEADER} header is required.",
            details={"field": IDEMPOTENCY_KEY_HEADER, "reason": "missing"},
        )
    if len(raw) > IDEMPOTENCY_KEY_MAX_LENGTH:
        raise ValidationError(
            f"{IDEMPOTENCY_KEY_HEADER} must be at most {IDEMPOTENCY_KEY_MAX_LENGTH} characters.",
            details={
                "field": IDEMPOTENCY_KEY_HEADER,
                "reason": "too long",
                "max_length": IDEMPOTENCY_KEY_MAX_LENGTH,
            },
        )
    if any(not 0x21 <= ord(character) <= 0x7E for character in raw):
        raise ValidationError(
            f"{IDEMPOTENCY_KEY_HEADER} must contain visible ASCII characters only.",
            details={"field": IDEMPOTENCY_KEY_HEADER, "reason": "invalid characters"},
        )
    return raw


def build_router(store: Store) -> APIRouter:
    router = APIRouter(tags=["cart"])

    @router.get(
        "/cart",
        response_model=Cart,
        summary="Current cart with the total item count",
    )
    async def get_cart() -> Cart:
        return store.get_cart()

    @router.post(
        "/cart/items",
        status_code=201,
        response_model=AddCartItemResponse,
        summary="Add a SKU and quantity to the cart",
        responses={
            201: {
                "model": AddCartItemResponse,
                "description": "Added to the cart. A replay -- same Idempotency-Key, same "
                "body -- returns this identical status code and body, with the "
                "`Idempotency-Replayed: true` header as the only signal that the cart was "
                "not touched twice. A rejected first attempt is replayed the same way, "
                "with its original 404/409.",
            },
            400: {"description": "VALIDATION_ERROR -- missing/malformed key, or invalid body."},
            404: {"description": "SKU_NOT_FOUND"},
            409: {
                "description": "INSUFFICIENT_STOCK, or IDEMPOTENCY_KEY_CONFLICT when the "
                "key was reused with a different body."
            },
        },
    )
    async def add_cart_item(payload: AddCartItemRequest, request: Request) -> Response:
        idempotency_key = require_idempotency_key(request)
        outcome = await store.add_to_cart(
            sku_id=payload.sku_id,
            quantity=payload.quantity,
            idempotency_key=idempotency_key,
            request_id=request_id_of(request),
        )

        response = JSONResponse(status_code=outcome.status_code, content=outcome.body)
        if outcome.replayed:
            # A replay is byte-identical to the original response and reports the
            # same status code, so this header is the only in-band signal that the
            # cart was not touched a second time.
            response.headers[REPLAYED_HEADER] = "true"
        return response

    return router
