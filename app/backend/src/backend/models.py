"""API-facing data shapes.

Two decisions drive what lives here:

* The catalog projection (`Product`) carries everything the client needs to render
  a PDP in a single round trip -- product, dimensions and every SKU. Resolving a
  variant locally is what makes stale UI on the client structurally impossible.
* The add-to-cart request model forbids unknown fields. A client that sends a price
  or a stock figure gets a 400 rather than having it quietly ignored, which is a
  stronger guarantee than "we don't read it".
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .config import MAX_QUANTITY_PER_REQUEST


class OptionValue(BaseModel):
    """One selectable value of one dimension."""

    value: str
    label: str
    # Only meaningful for dimensions with a visual identity (colour); the UI uses
    # it to render a swatch instead of a text-only chip.
    swatch: str | None = None


class OptionDimension(BaseModel):
    key: str
    label: str
    values: list[OptionValue]


class Sku(BaseModel):
    """A sellable variant as seen by the client."""

    id: str
    options: dict[str, str]
    price_minor: int
    currency: str
    available_quantity: int
    # Derived on the server so the client never re-implements the
    # "available == 0 means out of stock" rule and gets it subtly wrong.
    in_stock: bool
    image_url: str


class Product(BaseModel):
    id: str
    name: str
    description: str
    currency: str
    hero_image_url: str
    option_dimensions: list[OptionDimension]
    skus: list[Sku]


class AddCartItemRequest(BaseModel):
    """Body of ``POST /api/cart/items``.

    ``extra="forbid"`` is where "never trust price or stock sent by the client" is
    actually enforced: attempting to send them is an error, not a silent no-op.
    """

    model_config = ConfigDict(extra="forbid")

    sku_id: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=1, le=MAX_QUANTITY_PER_REQUEST)


class CartLine(BaseModel):
    sku_id: str
    quantity: int
    unit_price_minor: int
    line_total_minor: int
    # Human-readable summary, composed server-side so the cart can be rendered
    # without the client also holding the product payload.
    name: str
    image_url: str
    options: dict[str, str]


class Cart(BaseModel):
    id: str
    currency: str
    items: list[CartLine]
    # Sum of line quantities -- a count of items, not of lines.
    total_item_count: int
    subtotal_minor: int


class SkuAvailability(BaseModel):
    sku_id: str
    available_quantity: int


class AddCartItemResponse(BaseModel):
    cart: Cart
    # Inlined so the client can refresh its stock figure from the add-to-cart
    # response itself rather than issuing a second request.
    sku_availability: SkuAvailability


class HealthResponse(BaseModel):
    status: str
    version: str
