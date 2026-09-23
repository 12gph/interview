/**
 * The product detail page: data loading, selection, quantity, and the add-to-cart
 * transaction.
 *
 * Everything the UI shows about the chosen variant is derived from a single
 * `selectedSku`. There is no second copy of the price, the image or the stock count to
 * keep in step, which makes "changed the options but the price stayed the same"
 * impossible rather than merely unlikely. The one extra piece of state is
 * `availabilityOverrides` -- stock figures the server reported later than the catalog
 * fetch. Those are newer truths, not a parallel store.
 *
 * The transient states are all here too: incomplete selection, unavailable combination,
 * out of stock, request in flight, and the three failure modes.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ApiClient } from "../api/client";
import { toApiRequestError } from "../api/errors";
import { newIdempotencyKey } from "../api/idempotency";
import { clampQuantity } from "../domain/quantity";
import type { PartialOptionSelection, Product, Sku } from "../domain/types";
import {
  imageAltText,
  isSelectionComplete,
  missingDimensions,
  resolveSku,
} from "../domain/variant";
import type { UseCartResult } from "../hooks/useCart";
import { useCart } from "../hooks/useCart";
import { useProduct } from "../hooks/useProduct";
import { AddToCartButton } from "./AddToCartButton";
import { CartSummary } from "./CartSummary";
import { OptionSelector } from "./OptionSelector";
import { ProductGallery } from "./ProductGallery";
import { ProductInfo } from "./ProductInfo";
import { QuantityStepper } from "./QuantityStepper";
import type { FeedbackTone } from "./StatusRegion";
import { StatusRegion } from "./StatusRegion";
import { LoadErrorState } from "./states/LoadErrorState";
import { LoadingState } from "./states/LoadingState";

export interface ProductPageProps {
  readonly client: ApiClient;
  readonly productId: string;
}

export function ProductPage({ client, productId }: ProductPageProps) {
  const { state, reload } = useProduct(client, productId);
  const cart = useCart(client);

  if (state.status === "loading") {
    return <LoadingState />;
  }

  if (state.status === "error") {
    return <LoadErrorState error={state.error} onRetry={reload} />;
  }

  // Mounted only once a product exists, so selection state can never outlive a refresh
  // and describe a catalog that has moved on.
  return <ProductDetail product={state.product} cart={cart} onRefreshProduct={reload} />;
}

interface Feedback {
  readonly message: string;
  readonly tone: FeedbackTone;
}

/**
 * A failed add, remembered so a retry reuses its idempotency key.
 *
 * Reusing the key is the whole point of the header: if the first attempt actually
 * succeeded but the response never arrived, retrying with the same key returns the
 * original outcome instead of adding a second time. A different SKU or quantity is a
 * different intent and gets a fresh key.
 */
interface FailedAttempt {
  readonly skuId: string;
  readonly quantity: number;
  readonly key: string;
}

interface ProductDetailProps {
  readonly product: Product;
  readonly cart: UseCartResult;
  readonly onRefreshProduct: () => void;
}

function ProductDetail({ product, cart, onRefreshProduct }: ProductDetailProps) {
  const [selection, setSelection] = useState<PartialOptionSelection>({});
  const [quantity, setQuantity] = useState(1);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [pending, setPending] = useState(false);
  const [availabilityOverrides, setAvailabilityOverrides] = useState<Record<string, number>>({});

  // Synchronous, unlike `pending`: two clicks dispatched in one batch both observe the
  // same state value, so only a ref can reject the second one.
  const submittingRef = useRef(false);
  const failedAttemptRef = useRef<FailedAttempt | null>(null);
  const skipClampNoticeRef = useRef(false);

  const { addItem, refresh: refreshCart } = cart;

  const selectedSku = useMemo<Sku | null>(() => {
    const resolved = resolveSku(product, selection);
    if (resolved === null) {
      return null;
    }
    const override = availabilityOverrides[resolved.id];
    if (override === undefined) {
      return resolved;
    }
    return { ...resolved, availableQuantity: override, inStock: override > 0 };
  }, [product, selection, availabilityOverrides]);

  const selectionComplete = isSelectionComplete(product, selection);
  const missingDimensionLabels = missingDimensions(product, selection).map(
    (dimension) => dimension.label,
  );
  const purchasable = selectedSku !== null && selectedSku.availableQuantity > 0;

  // Re-clamped whenever the SKU changes, not only when the field is edited. Switching
  // from a variant with plenty of stock to one with a single unit has to bring the
  // quantity down with it, and staying silent about that would make the number appear to
  // change on its own.
  useEffect(() => {
    if (selectedSku === null) {
      return;
    }
    const clamped = clampQuantity(quantity, selectedSku.availableQuantity);
    if (clamped === quantity) {
      return;
    }
    setQuantity(clamped);

    // The out-of-stock path already explained itself and corrected the figure; letting
    // this notice overwrite it would hide why nothing was added.
    if (skipClampNoticeRef.current) {
      skipClampNoticeRef.current = false;
      return;
    }
    setFeedback({
      tone: "info",
      message:
        selectedSku.availableQuantity > 0
          ? `Quantity adjusted to ${clamped} — only ${selectedSku.availableQuantity} left.`
          : `Quantity reset to ${clamped} — this variant is now out of stock.`,
    });
  }, [quantity, selectedSku]);

  const handleSelect = useCallback((dimensionKey: string, value: string) => {
    setSelection((current) => ({ ...current, [dimensionKey]: value }));
    setFeedback(null);
    failedAttemptRef.current = null;
  }, []);

  const handleRefresh = useCallback(() => {
    onRefreshProduct();
    refreshCart();
    setFeedback(null);
    failedAttemptRef.current = null;
  }, [onRefreshProduct, refreshCart]);

  const handleAddToCart = useCallback(async () => {
    if (submittingRef.current) {
      return;
    }
    if (selectedSku === null || selectedSku.availableQuantity <= 0) {
      return;
    }

    const skuId = selectedSku.id;
    const previous = failedAttemptRef.current;
    const key =
      previous !== null && previous.skuId === skuId && previous.quantity === quantity
        ? previous.key
        : newIdempotencyKey();

    submittingRef.current = true;
    setPending(true);
    setFeedback(null);

    try {
      const result = await addItem({ skuId, quantity, idempotencyKey: key });
      failedAttemptRef.current = null;
      setAvailabilityOverrides((current) => ({
        ...current,
        [result.availability.skuId]: result.availability.availableQuantity,
      }));
      setFeedback({
        tone: "success",
        message: result.replayed
          ? "Already in your cart — nothing was added twice."
          : `Added to cart. ${result.availability.availableQuantity} left.`,
      });
    } catch (cause: unknown) {
      const error = toApiRequestError(cause);
      failedAttemptRef.current = { skuId, quantity, key };

      // Copied out of `error.details` first: the narrowing below does not survive into
      // the state updater closure.
      const available = error.details.available;

      if (error.code === "INSUFFICIENT_STOCK" && available !== undefined) {
        // Adopt the server's figure and let the clamp effect bring the quantity down to
        // match, so the form is immediately in a state that can succeed.
        skipClampNoticeRef.current = true;
        setAvailabilityOverrides((current) => ({ ...current, [skuId]: available }));
        setFeedback({
          tone: "error",
          message: `Only ${available} left — quantity adjusted. Try adding again.`,
        });
      } else {
        setFeedback({ tone: "error", message: error.message });
      }
    } finally {
      submittingRef.current = false;
      setPending(false);
    }
  }, [addItem, quantity, selectedSku]);

  const imageUrl = selectedSku === null ? product.heroImageUrl : selectedSku.imageUrl;
  const altText =
    selectedSku === null ? `${product.name}, no variant selected` : imageAltText(product, selection);

  return (
    <article className="pdp">
      <div className="pdp__main">
        <ProductGallery imageUrl={imageUrl} alt={altText} />

        <section className="pdp__buy">
          <ProductInfo
            product={product}
            sku={selectedSku}
            missingDimensionLabels={missingDimensionLabels}
          />

          <div className="pdp__options">
            {product.optionDimensions.map((dimension) => (
              <OptionSelector
                key={dimension.key}
                product={product}
                dimension={dimension}
                selection={selection}
                onSelect={handleSelect}
              />
            ))}
          </div>

          <QuantityStepper
            quantity={quantity}
            availableQuantity={selectedSku === null ? 0 : selectedSku.availableQuantity}
            disabled={selectedSku === null}
            onChange={setQuantity}
          />

          <AddToCartButton
            pending={pending}
            disabled={!purchasable}
            onClick={() => {
              void handleAddToCart();
            }}
          />

          {selectionComplete && !purchasable && selectedSku === null && (
            <p className="pdp__note">
              That combination isn&rsquo;t made. Choose another colour or size.
            </p>
          )}

          <StatusRegion message={feedback === null ? null : feedback.message} tone={feedback === null ? "info" : feedback.tone} />

          <button type="button" className="pdp__refresh" onClick={handleRefresh}>
            Refresh availability
          </button>
        </section>
      </div>

      <CartSummary
        cart={cart.cart}
        loading={cart.loading}
        error={cart.error}
        onRefresh={refreshCart}
      />
    </article>
  );
}
