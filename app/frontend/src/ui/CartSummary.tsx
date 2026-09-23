/**
 * Cart contents.
 *
 * The line items come straight from the server's cart response; nothing here recomputes
 * a total or tracks a count of its own. That is what makes "add to cart incremented the
 * badge" true by construction rather than by a patch applied in the right order.
 */

import type { ApiRequestError } from "../api/errors";
import { formatMinorUnits } from "../domain/money";
import type { Cart } from "../domain/types";

export interface CartSummaryProps {
  readonly cart: Cart | null;
  readonly loading: boolean;
  readonly error: ApiRequestError | null;
  readonly onRefresh: () => void;
}

export function CartSummary({ cart, loading, error, onRefresh }: CartSummaryProps) {
  return (
    <aside className="cart" aria-labelledby="cart-heading">
      <div className="cart__header">
        <h2 className="cart__title" id="cart-heading">
          Cart
        </h2>
        <button
          type="button"
          className="cart__refresh"
          onClick={onRefresh}
          aria-label="Refresh cart"
        >
          Refresh
        </button>
      </div>

      {loading && cart === null && <p className="cart__state">Loading cart…</p>}

      {error !== null && (
        <p className="cart__state cart__state--error" role="alert">
          {error.message}
        </p>
      )}

      {cart !== null && (
        <>
          <p className="cart__count">
            {cart.totalItemCount === 1 ? "1 item" : `${cart.totalItemCount} items`}
          </p>

          {cart.items.length === 0 ? (
            <p className="cart__state">Your cart is empty.</p>
          ) : (
            <ul className="cart__lines">
              {cart.items.map((line) => (
                <li className="cart__line" key={line.skuId}>
                  <img
                    className="cart__thumb"
                    src={line.imageUrl}
                    alt=""
                    width={40}
                    height={48}
                  />
                  <span className="cart__line-name">{line.name}</span>
                  <span className="cart__line-quantity">×{line.quantity}</span>
                  <span className="cart__line-total">
                    {formatMinorUnits(line.lineTotalMinor, cart.currency)}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <p className="cart__subtotal">
            <span>Subtotal</span>
            <span>{formatMinorUnits(cart.subtotalMinor, cart.currency)}</span>
          </p>
        </>
      )}
    </aside>
  );
}
