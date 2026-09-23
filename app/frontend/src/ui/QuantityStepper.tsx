/**
 * Quantity input with stepper buttons.
 *
 * The component does not decide what a legal quantity is -- `domain/quantity.ts` does,
 * and both the arrows and the typed value go through it. Keeping the rule in one place
 * is what stops the field from accepting "9" for a SKU with two units left.
 */

import { clampQuantity, quantityBounds } from "../domain/quantity";

export interface QuantityStepperProps {
  readonly quantity: number;
  readonly availableQuantity: number;
  readonly disabled: boolean;
  readonly onChange: (quantity: number) => void;
}

export function QuantityStepper({
  quantity,
  availableQuantity,
  disabled,
  onChange,
}: QuantityStepperProps) {
  const bounds = quantityBounds(availableQuantity);
  const inputId = "pdp-quantity";

  return (
    <div className="quantity">
      <label className="quantity__label" htmlFor={inputId}>
        Quantity
      </label>
      <div className="quantity__controls">
        <button
          type="button"
          className="quantity__button"
          aria-label="Decrease quantity"
          disabled={disabled || quantity <= bounds.min}
          onClick={() => {
            onChange(clampQuantity(quantity - 1, availableQuantity));
          }}
        >
          &minus;
        </button>
        <input
          id={inputId}
          className="quantity__input"
          type="number"
          inputMode="numeric"
          min={bounds.min}
          max={bounds.max}
          value={quantity}
          disabled={disabled}
          onChange={(event) => {
            const parsed = Number.parseInt(event.target.value, 10);
            if (Number.isNaN(parsed)) {
              // An empty field mid-edit: leave the last legal value alone rather than
              // snapping to 1 while the shopper is still typing.
              return;
            }
            onChange(clampQuantity(parsed, availableQuantity));
          }}
        />
        <button
          type="button"
          className="quantity__button"
          aria-label="Increase quantity"
          disabled={disabled || quantity >= bounds.max}
          onClick={() => {
            onChange(clampQuantity(quantity + 1, availableQuantity));
          }}
        >
          +
        </button>
      </div>
      <p className="quantity__hint">
        {availableQuantity > 0 ? `${availableQuantity} available` : "Out of stock"}
      </p>
    </div>
  );
}
