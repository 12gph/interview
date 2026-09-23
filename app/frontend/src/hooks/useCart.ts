/**
 * Cart state.
 *
 * Every cart value shown in the UI comes from the server's own response -- the add
 * response carries the whole cart, so there is no need to patch a local copy and no
 * chance of the two drifting apart.
 */

import { useCallback, useEffect, useState } from "react";

import type { AddToCartInput, ApiClient } from "../api/client";
import type { ApiRequestError } from "../api/errors";
import { toApiRequestError } from "../api/errors";
import type { AddToCartResult, Cart } from "../domain/types";

export interface UseCartResult {
  readonly cart: Cart | null;
  readonly loading: boolean;
  readonly error: ApiRequestError | null;
  readonly refresh: () => void;
  /** Throws ApiRequestError on failure; the caller decides how to present it. */
  readonly addItem: (input: AddToCartInput) => Promise<AddToCartResult>;
}

export function useCart(client: ApiClient): UseCartResult {
  const [cart, setCart] = useState<Cart | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiRequestError | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    client.getCart().then(
      (next) => {
        if (!cancelled) {
          setCart(next);
          setLoading(false);
        }
      },
      (cause: unknown) => {
        if (!cancelled) {
          setError(toApiRequestError(cause));
          setLoading(false);
        }
      },
    );

    return () => {
      cancelled = true;
    };
  }, [client, attempt]);

  const refresh = useCallback(() => {
    setAttempt((current) => current + 1);
  }, []);

  const addItem = useCallback(
    async (input: AddToCartInput): Promise<AddToCartResult> => {
      const result = await client.addToCart(input);
      // The response is authoritative: adopt it rather than incrementing a counter.
      setCart(result.cart);
      return result;
    },
    [client],
  );

  return { cart, loading, error, refresh, addItem };
}
