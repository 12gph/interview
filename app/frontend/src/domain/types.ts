/**
 * Domain models.
 *
 * These are the shapes the rest of the app works with: `camelCase`, read-only and
 * deliberately independent of how the API spells things. The translation from the
 * wire format lives in `api/client.ts`, which is the only module that knows both.
 */

export interface OptionValue {
  readonly value: string;
  readonly label: string;
  /** Present for dimensions with a visual identity; null elsewhere. */
  readonly swatch: string | null;
}

export interface OptionDimension {
  readonly key: string;
  readonly label: string;
  readonly values: readonly OptionValue[];
}

/** A partial (or complete) choice of one value per dimension. */
export type PartialOptionSelection = Record<string, string | undefined>;

/** A complete choice: every dimension resolved to a value. */
export type OptionSelection = Record<string, string>;

export interface Sku {
  readonly id: string;
  readonly options: OptionSelection;
  readonly priceMinor: number;
  readonly currency: string;
  /** Authoritative server figure. The client never derives this itself. */
  readonly availableQuantity: number;
  readonly inStock: boolean;
  readonly imageUrl: string;
}

export interface Product {
  readonly id: string;
  readonly name: string;
  readonly description: string;
  readonly currency: string;
  readonly heroImageUrl: string;
  readonly optionDimensions: readonly OptionDimension[];
  readonly skus: readonly Sku[];
}

export interface CartLine {
  readonly skuId: string;
  readonly quantity: number;
  readonly unitPriceMinor: number;
  readonly lineTotalMinor: number;
  readonly name: string;
  readonly imageUrl: string;
  readonly options: OptionSelection;
}

export interface Cart {
  readonly id: string;
  readonly currency: string;
  readonly items: readonly CartLine[];
  readonly totalItemCount: number;
  readonly subtotalMinor: number;
}

export interface SkuAvailability {
  readonly skuId: string;
  readonly availableQuantity: number;
}

export interface AddToCartResult {
  readonly cart: Cart;
  readonly availability: SkuAvailability;
  /**
   * True when the server recognised the Idempotency-Key and replayed the stored
   * response instead of applying the add a second time. Surfaced to the UI because it
   * is the difference between "we added it" and "it was already added".
   */
  readonly replayed: boolean;
}
