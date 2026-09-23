/**
 * The product could not be loaded.
 *
 * Retry re-runs the same request rather than reloading the page, so the shopper is not
 * thrown back to an empty screen. The wording separates "worth trying again" from "this
 * is probably permanent", because telling someone to retry a 404 wastes their time.
 */

import type { ApiRequestError } from "../../api/errors";

export interface LoadErrorStateProps {
  readonly error: ApiRequestError;
  readonly onRetry: () => void;
}

export function LoadErrorState({ error, onRetry }: LoadErrorStateProps) {
  return (
    <div className="state state--error" role="alert">
      <h2 className="state__title">We couldn&rsquo;t load this product</h2>
      <p className="state__text">{error.message}</p>
      <p className="state__hint">
        {error.isRetryable
          ? "This looks like a temporary problem."
          : "This product may no longer be available."}
      </p>
      <button type="button" className="state__retry" onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}
