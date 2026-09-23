/**
 * Money formatting.
 *
 * Amounts travel as integer minor units end to end so no rounding error can creep in;
 * the division by 100 happens exactly once, here, at the point where a human reads it.
 */

const formatters = new Map<string, Intl.NumberFormat>();

function formatterFor(currency: string): Intl.NumberFormat {
  const existing = formatters.get(currency);
  if (existing !== undefined) {
    return existing;
  }
  const created = new Intl.NumberFormat("en-US", { style: "currency", currency });
  formatters.set(currency, created);
  return created;
}

export function formatMinorUnits(amountMinor: number, currency: string): string {
  return formatterFor(currency).format(amountMinor / 100);
}
