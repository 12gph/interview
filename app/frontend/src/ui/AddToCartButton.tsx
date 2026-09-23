/**
 * The primary call to action.
 *
 * `disabled` carries "the current selection cannot be bought"; `pending` carries "a
 * request is in flight". They are separate because the reasons are separate: a
 * disabled-for-stock button and a busy button need different announcements.
 *
 * The `disabled` attribute is the visible half of the duplicate-submit defence; the
 * half that actually holds is the ref guard in `ProductPage`, since two clicks
 * dispatched in the same batch can both read a stale `pending` state.
 */

export interface AddToCartButtonProps {
  readonly pending: boolean;
  readonly disabled: boolean;
  readonly onClick: () => void;
}

export function AddToCartButton({ pending, disabled, onClick }: AddToCartButtonProps) {
  return (
    <button
      type="button"
      className="add-to-cart"
      onClick={onClick}
      disabled={disabled || pending}
      aria-busy={pending}
    >
      {pending ? "Adding…" : "Add to cart"}
    </button>
  );
}
