/**
 * Product fetching with an explicit retry.
 *
 * The hook owns exactly one question -- "where did the product come from" -- and
 * nothing about variants or carts. Splitting it that way is what lets the retry and
 * error states be reasoned about without dragging selection state along.
 */

import { useCallback, useEffect, useState } from "react";

import type { ApiClient } from "../api/client";
import type { ApiRequestError } from "../api/errors";
import { toApiRequestError } from "../api/errors";
import type { Product } from "../domain/types";

export type ProductLoadState =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly product: Product }
  | { readonly status: "error"; readonly error: ApiRequestError };

export interface UseProductResult {
  readonly state: ProductLoadState;
  /** Re-run the fetch. Backs both the Retry button and the Refresh control. */
  readonly reload: () => void;
}

export function useProduct(client: ApiClient, productId: string): UseProductResult {
  const [state, setState] = useState<ProductLoadState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    // A reload or a fast unmount can leave an older request in flight; without this
    // flag its response would land last and overwrite the newer one.
    let cancelled = false;
    setState({ status: "loading" });

    client.getProduct(productId).then(
      (product) => {
        if (!cancelled) {
          setState({ status: "ready", product });
        }
      },
      (cause: unknown) => {
        if (!cancelled) {
          setState({ status: "error", error: toApiRequestError(cause) });
        }
      },
    );

    return () => {
      cancelled = true;
    };
  }, [client, productId, attempt]);

  const reload = useCallback(() => {
    setAttempt((current) => current + 1);
  }, []);

  return { state, reload };
}
