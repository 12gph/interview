/**
 * One option dimension, rendered as a radio group.
 *
 * Native radios rather than styled buttons with ARIA roles: arrow-key navigation, Tab
 * into the group, and screen-reader semantics all come for free, and there is no
 * roving-tabindex logic to get subtly wrong.
 *
 * Note the two distinct disabled states. An *impossible* combination is disabled --
 * there is no SKU behind it. An *out of stock* variant stays selectable, because the
 * brief asks for it to be shown as its own state rather than hidden; the add-to-cart
 * button is what refuses the purchase. Collapsing the two would silently drop one of
 * the two required states.
 */

import type { OptionDimension, PartialOptionSelection, Product } from "../domain/types";
import type { OptionValueState } from "../domain/variant";
import { optionValueState } from "../domain/variant";

export interface OptionSelectorProps {
  readonly product: Product;
  readonly dimension: OptionDimension;
  readonly selection: PartialOptionSelection;
  readonly onSelect: (dimensionKey: string, value: string) => void;
}

/** Text, not colour alone, so the distinction survives colour blindness. */
const STATE_NOTE: Record<OptionValueState, string | null> = {
  available: null,
  out_of_stock: "Out of stock",
  impossible: "Not available",
};

export function OptionSelector({
  product,
  dimension,
  selection,
  onSelect,
}: OptionSelectorProps) {
  const selected = selection[dimension.key];

  return (
    <fieldset className="option">
      <legend className="option__legend">{dimension.label}</legend>
      <div className="option__values">
        {dimension.values.map((value) => {
          const state = optionValueState(product, selection, dimension.key, value.value);
          const note = STATE_NOTE[state];
          const isSelected = selected === value.value;

          return (
            <label
              key={value.value}
              className={[
                "option__value",
                `option__value--${state}`,
                isSelected ? "option__value--selected" : "",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              <input
                className="option__input"
                type="radio"
                name={dimension.key}
                value={value.value}
                checked={isSelected}
                disabled={state === "impossible"}
                // Spelled out rather than inherited from the label: the label's text runs
                // the value and the note together with no separator, which screen readers
                // announce as one word ("SOut of stock").
                aria-label={note === null ? value.label : `${value.label} — ${note}`}
                onChange={() => {
                  onSelect(dimension.key, value.value);
                }}
              />
              {value.swatch !== null && (
                <span
                  className="option__swatch"
                  style={{ backgroundColor: value.swatch }}
                  aria-hidden="true"
                />
              )}
              <span className="option__label">{value.label}</span>
              {note !== null && <span className="option__note">{note}</span>}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
