/**
 * Name, description, price and stock status.
 *
 * All three changeable values are passed in already resolved. The component never
 * looks at the SKU list, which is the point: price, availability and the quantity cap
 * all come from one `resolveSku` call upstream, so they cannot disagree with each
 * other or lag one render behind the selection.
 *
 * An incomplete selection is its own state, not an error: the price slot explains what
 * is still missing instead of showing a number for a variant nobody picked.
 */

import { formatMinorUnits } from "../domain/money";
import type { Product, Sku } from "../domain/types";

export interface ProductInfoProps {
  readonly product: Product;
  readonly sku: Sku | null;
  /** Labels of the dimensions still unchosen, in display order. */
  readonly missingDimensionLabels: readonly string[];
}

function stockMessage(sku: Sku | null): string {
  if (sku === null) {
    return "";
  }
  if (sku.availableQuantity <= 0) {
    return "Out of stock";
  }
  if (sku.availableQuantity <= 3) {
    return `Only ${sku.availableQuantity} left`;
  }
  return "In stock";
}

export function ProductInfo({ product, sku, missingDimensionLabels }: ProductInfoProps) {
  const price = sku === null ? null : formatMinorUnits(sku.priceMinor, product.currency);
  const stock = stockMessage(sku);

  return (
    <div className="info">
      <h1 className="info__name">{product.name}</h1>
      <p className="info__description">{product.description}</p>

      <p className="info__price" aria-live="polite">
        {price !== null ? (
          <span className="info__amount">{price}</span>
        ) : missingDimensionLabels.length > 0 ? (
          <span className="info__prompt">Select {missingDimensionLabels.join(" and ")}</span>
        ) : (
          // Every dimension is chosen and no SKU matches, so this is a real gap in the
          // catalog rather than a half-finished selection.
          <span className="info__prompt">This combination isn&rsquo;t available</span>
        )}
      </p>

      {stock !== "" && (
        <p className={sku !== null && sku.availableQuantity <= 0 ? "info__stock info__stock--out" : "info__stock"}>
          {stock}
        </p>
      )}
    </div>
  );
}
