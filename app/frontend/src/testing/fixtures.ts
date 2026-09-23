/**
 * Test fixtures.
 *
 * The catalog mirrors the backend seed exactly -- same seven SKUs, same two impossible
 * combinations (black/L and sage/S), same missing sand/S. Keeping them in step means a
 * component test failing here points at the component rather than at a drifted fixture.
 */

import type { AddToCartInput, ApiClient } from "../api/client";
import type { AddToCartResult, Cart, OptionSelection, Product, Sku } from "../domain/types";

function sku(
  id: string,
  options: OptionSelection,
  priceMinor: number,
  availableQuantity: number,
): Sku {
  // Mirrors the backend seed's naming so a snapshot of the rendered src is meaningful.
  const colour = options["colour"] ?? "unknown";
  const size = options["size"] ?? "unknown";
  return {
    id,
    options,
    priceMinor,
    currency: "USD",
    availableQuantity,
    inStock: availableQuantity > 0,
    imageUrl: `/images/tee-${colour}-${size}.svg`,
  };
}

export const TEST_PRODUCT: Product = {
  id: "aurora-tee",
  name: "Aurora Classic Tee",
  description: "Midweight organic cotton tee.",
  currency: "USD",
  heroImageUrl: "/images/aurora-tee-hero.svg",
  optionDimensions: [
    {
      key: "colour",
      label: "Colour",
      values: [
        { value: "black", label: "Black", swatch: "#232323" },
        { value: "sand", label: "Sand", swatch: "#d9c9a8" },
        { value: "sage", label: "Sage", swatch: "#9caf88" },
      ],
    },
    {
      key: "size",
      label: "Size",
      values: [
        { value: "s", label: "S", swatch: null },
        { value: "m", label: "M", swatch: null },
        { value: "l", label: "L", swatch: null },
      ],
    },
  ],
  skus: [
    sku("TEE-BLK-S", { colour: "black", size: "s" }, 4900, 4),
    sku("TEE-BLK-M", { colour: "black", size: "m" }, 4900, 2),
    // Deliberately out of stock: an existing variant with no units is a state the brief
    // requires to be shown, and it is not the same as an impossible combination.
    sku("TEE-SND-S", { colour: "sand", size: "s" }, 5300, 0),
    sku("TEE-SND-M", { colour: "sand", size: "m" }, 5300, 6),
    sku("TEE-SND-L", { colour: "sand", size: "l" }, 5300, 3),
    sku("TEE-SGE-M", { colour: "sage", size: "m" }, 5700, 1),
    sku("TEE-SGE-L", { colour: "sage", size: "l" }, 5700, 5),
  ],
};

export const EMPTY_CART: Cart = {
  id: "cart-1",
  currency: "USD",
  items: [],
  totalItemCount: 0,
  subtotalMinor: 0,
};

export function addResult(skuId: string, availableAfter: number): AddToCartResult {
  const match = TEST_PRODUCT.skus.find((candidate) => candidate.id === skuId);
  const unitPrice = match === undefined ? 0 : match.priceMinor;

  return {
    cart: {
      id: "cart-1",
      currency: "USD",
      items: [
        {
          skuId,
          quantity: 1,
          unitPriceMinor: unitPrice,
          lineTotalMinor: unitPrice,
          name: skuId,
          imageUrl: match === undefined ? "/images/aurora-tee-hero.svg" : match.imageUrl,
          options: {},
        },
      ],
      totalItemCount: 1,
      subtotalMinor: unitPrice,
    },
    availability: { skuId, availableQuantity: availableAfter },
    replayed: false,
  };
}

/** A client that never touches the network; every method can be overridden per test. */
export function fakeClient(overrides: Partial<ApiClient> = {}): ApiClient {
  return {
    getProduct: () => Promise.resolve(TEST_PRODUCT),
    getCart: () => Promise.resolve(EMPTY_CART),
    addToCart: (input: AddToCartInput) => {
      const match = TEST_PRODUCT.skus.find((candidate) => candidate.id === input.skuId);
      const remaining = match === undefined ? 0 : match.availableQuantity - input.quantity;
      return Promise.resolve(addResult(input.skuId, Math.max(0, remaining)));
    },
    ...overrides,
  };
}
