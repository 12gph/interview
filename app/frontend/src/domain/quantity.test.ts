/** Quantity rule tests. */

import { describe, expect, it } from "vitest";

import { clampQuantity, isQuantityValid, quantityBounds } from "./quantity";

describe("quantityBounds", () => {
  it("caps at the available quantity", () => {
    expect(quantityBounds(5)).toEqual({ min: 1, max: 5 });
  });

  it("never produces an inverted range when nothing is available", () => {
    expect(quantityBounds(0)).toEqual({ min: 1, max: 1 });
    expect(quantityBounds(-3)).toEqual({ min: 1, max: 1 });
  });
});

describe("clampQuantity", () => {
  it("leaves a legal quantity alone", () => {
    expect(clampQuantity(3, 5)).toBe(3);
  });

  it("brings an over-large quantity down to the cap", () => {
    expect(clampQuantity(9, 2)).toBe(2);
    expect(clampQuantity(6, 1)).toBe(1);
  });

  it("floors at one, because zero is not a quantity the shopper can buy", () => {
    expect(clampQuantity(0, 5)).toBe(1);
    expect(clampQuantity(-4, 5)).toBe(1);
  });

  it("falls back to the minimum for values that are not finite numbers", () => {
    expect(clampQuantity(Number.NaN, 5)).toBe(1);
    // Infinity is not a quantity anyone can buy, so it lands on the floor rather than
    // being treated as "very large" and clamped to the cap.
    expect(clampQuantity(Number.POSITIVE_INFINITY, 5)).toBe(1);
  });

  it("truncates fractions rather than inventing half a unit", () => {
    expect(clampQuantity(2.7, 5)).toBe(2);
  });

  it("returns 1 when the variant is sold out", () => {
    expect(clampQuantity(4, 0)).toBe(1);
  });
});

describe("isQuantityValid", () => {
  it("accepts only whole numbers inside the bounds", () => {
    expect(isQuantityValid(2, 5)).toBe(true);
    expect(isQuantityValid(0, 5)).toBe(false);
    expect(isQuantityValid(6, 5)).toBe(false);
    expect(isQuantityValid(2.5, 5)).toBe(false);
  });
});
