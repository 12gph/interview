/**
 * Variant resolution: turning a set of option choices into a concrete SKU.
 *
 * Pure functions, no React and no network, because this is the part of the PDP most
 * likely to be wrong and the cheapest to test exhaustively.
 */

import type { OptionDimension, PartialOptionSelection, Product, Sku } from "./types";

/**
 * Whether a value can be chosen, and if not, why.
 *
 * The "why" carries a requirement: the brief lists impossible combinations and
 * out-of-stock SKUs as two separate states to render, so collapsing them into a single
 * boolean would silently drop one of them.
 */
export type OptionValueState = "available" | "out_of_stock" | "impossible";

function definedEntries(selection: PartialOptionSelection): [string, string][] {
  const entries: [string, string][] = [];
  for (const [key, value] of Object.entries(selection)) {
    if (value !== undefined) {
      entries.push([key, value]);
    }
  }
  return entries;
}

export function isSelectionComplete(product: Product, selection: PartialOptionSelection): boolean {
  return product.optionDimensions.every((dimension) => {
    const chosen = selection[dimension.key];
    return chosen !== undefined && dimension.values.some((value) => value.value === chosen);
  });
}

/**
 * The SKU matching a complete selection, or null.
 *
 * null is genuinely ambiguous on its own -- "nothing chosen yet" versus "this
 * combination is not made" -- so callers must pair it with `isSelectionComplete` to
 * tell the two apart. Which one they are looking at decides which of the two required
 * states gets rendered.
 */
export function resolveSku(product: Product, selection: PartialOptionSelection): Sku | null {
  if (!isSelectionComplete(product, selection)) {
    return null;
  }

  return (
    product.skus.find((sku) =>
      product.optionDimensions.every(
        (dimension) => sku.options[dimension.key] === selection[dimension.key],
      ),
    ) ?? null
  );
}

/**
 * State of `value` in `dimensionKey`, holding every other dimension as chosen.
 *
 * Probing beats special-casing: temporarily assume the shopper picked this value and
 * ask what the catalog says. "Black + L is not made" then falls out of the data instead
 * of needing a rule per dimension.
 */
export function optionValueState(
  product: Product,
  selection: PartialOptionSelection,
  dimensionKey: string,
  value: string,
): OptionValueState {
  const probe: Record<string, string> = {};
  for (const [key, chosen] of definedEntries(selection)) {
    probe[key] = chosen;
  }
  probe[dimensionKey] = value;

  const candidates = product.skus.filter((sku) =>
    Object.entries(probe).every(([key, wanted]) => sku.options[key] === wanted),
  );

  if (candidates.length === 0) {
    return "impossible";
  }
  return candidates.some((sku) => sku.availableQuantity > 0) ? "available" : "out_of_stock";
}

/** Dimensions the shopper still has to choose, in display order. */
export function missingDimensions(
  product: Product,
  selection: PartialOptionSelection,
): OptionDimension[] {
  return product.optionDimensions.filter((dimension) => selection[dimension.key] === undefined);
}

/** Human-readable summary of the current selection, e.g. "Black / M". */
export function describeSelection(product: Product, selection: PartialOptionSelection): string {
  const parts: string[] = [];
  for (const dimension of product.optionDimensions) {
    const chosen = selection[dimension.key];
    if (chosen === undefined) {
      continue;
    }
    const match = dimension.values.find((value) => value.value === chosen);
    parts.push(match?.label ?? chosen);
  }
  return parts.join(" / ");
}

/**
 * Alt text that names the chosen variant.
 *
 * "Product image" tells a screen-reader user nothing here: the colour and the size are
 * precisely what changes between the seven images, so they are what the description has
 * to carry. Dimensions the shopper has not chosen yet are omitted rather than guessed.
 */
export function imageAltText(product: Product, selection: PartialOptionSelection): string {
  const parts: string[] = [];
  for (const dimension of product.optionDimensions) {
    const chosen = selection[dimension.key];
    if (chosen === undefined) {
      continue;
    }
    const match = dimension.values.find((value) => value.value === chosen);
    parts.push(`${dimension.label}: ${match?.label ?? chosen}`);
  }
  if (parts.length === 0) {
    return `${product.name}, no variant selected`;
  }
  return `${product.name} — ${parts.join(", ")}`;
}
