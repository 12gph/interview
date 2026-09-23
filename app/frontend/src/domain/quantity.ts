/** Quantity bounds. Kept separate from the components so the rule is testable alone. */

export const MIN_QUANTITY = 1;

export interface QuantityBounds {
  readonly min: number;
  readonly max: number;
}

/**
 * Bounds for a SKU.
 *
 * When nothing is available the bounds are [1, 1] rather than [1, 0]: the input still
 * has to hold a legal value, and it is the add-to-cart button (not an inverted range)
 * that communicates "cannot buy this".
 */
export function quantityBounds(availableQuantity: number): QuantityBounds {
  return {
    min: MIN_QUANTITY,
    max: Math.max(MIN_QUANTITY, Math.trunc(availableQuantity)),
  };
}

/**
 * Force a quantity into range.
 *
 * Called both when the shopper edits the field and whenever the selected SKU changes --
 * the second case is the one that is easy to forget, and forgetting it leaves a stale
 * quantity like "6" attached to a SKU with one unit left.
 */
export function clampQuantity(quantity: number, availableQuantity: number): number {
  const { min, max } = quantityBounds(availableQuantity);
  if (!Number.isFinite(quantity)) {
    return min;
  }
  return Math.min(Math.max(Math.trunc(quantity), min), max);
}

export function isQuantityValid(quantity: number, availableQuantity: number): boolean {
  const { min, max } = quantityBounds(availableQuantity);
  return Number.isInteger(quantity) && quantity >= min && quantity <= max;
}
