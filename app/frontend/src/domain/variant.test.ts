/**
 * Variant resolution unit tests.
 *
 * This is the part of the PDP most likely to be wrong and the cheapest to test, so it
 * gets the exhaustive treatment: pure functions, no rendering, one assertion per rule.
 */

import { describe, expect, it } from "vitest";

import { TEST_PRODUCT } from "../testing/fixtures";
import {
  imageAltText,
  isSelectionComplete,
  missingDimensions,
  optionValueState,
  resolveSku,
} from "./variant";

describe("isSelectionComplete", () => {
  it("is false until every dimension has a value", () => {
    expect(isSelectionComplete(TEST_PRODUCT, {})).toBe(false);
    expect(isSelectionComplete(TEST_PRODUCT, { colour: "black" })).toBe(false);
    expect(isSelectionComplete(TEST_PRODUCT, { colour: "black", size: "m" })).toBe(true);
  });

  it("does not accept a value that is not in the catalog", () => {
    expect(isSelectionComplete(TEST_PRODUCT, { colour: "taupe", size: "m" })).toBe(false);
  });
});

describe("resolveSku", () => {
  it("returns null while the selection is incomplete", () => {
    expect(resolveSku(TEST_PRODUCT, { colour: "black" })).toBeNull();
  });

  it("returns null for a combination that is not made", () => {
    // The catalog has no black/L.
    expect(resolveSku(TEST_PRODUCT, { colour: "black", size: "l" })).toBeNull();
  });

  it("returns the matching SKU, including an out-of-stock one", () => {
    expect(resolveSku(TEST_PRODUCT, { colour: "black", size: "m" })?.id).toBe("TEE-BLK-M");

    const soldOut = resolveSku(TEST_PRODUCT, { colour: "sand", size: "s" });
    expect(soldOut?.id).toBe("TEE-SND-S");
    expect(soldOut?.availableQuantity).toBe(0);
  });
});

describe("optionValueState", () => {
  it("reports available when a matching variant has stock", () => {
    expect(optionValueState(TEST_PRODUCT, {}, "colour", "black")).toBe("available");
  });

  it("distinguishes an out-of-stock variant from an impossible one", () => {
    // sand/S exists with zero units -- a real state to render, not a gap.
    expect(optionValueState(TEST_PRODUCT, {}, "colour", "sand")).toBe("available");
    expect(optionValueState(TEST_PRODUCT, { colour: "sand" }, "size", "s")).toBe("out_of_stock");

    // black/L is not made at all.
    expect(optionValueState(TEST_PRODUCT, { colour: "black" }, "size", "l")).toBe("impossible");
  });

  it("judges a value against the other dimensions as they are currently chosen", () => {
    // L is reachable in the abstract...
    expect(optionValueState(TEST_PRODUCT, {}, "size", "l")).toBe("available");
    // ...but not once black is pinned.
    expect(optionValueState(TEST_PRODUCT, { colour: "black" }, "size", "l")).toBe("impossible");
    // S is reachable, but not once sage is pinned.
    expect(optionValueState(TEST_PRODUCT, {}, "size", "s")).toBe("available");
    expect(optionValueState(TEST_PRODUCT, { colour: "sage" }, "size", "s")).toBe("impossible");
  });
});

describe("missingDimensions", () => {
  it("lists what is still unchosen, in display order", () => {
    expect(missingDimensions(TEST_PRODUCT, {}).map((d) => d.key)).toEqual(["colour", "size"]);
    expect(missingDimensions(TEST_PRODUCT, { colour: "black" }).map((d) => d.key)).toEqual(["size"]);
    expect(missingDimensions(TEST_PRODUCT, { colour: "black", size: "m" })).toEqual([]);
  });
});

describe("imageAltText", () => {
  it("names the chosen colour and size", () => {
    expect(imageAltText(TEST_PRODUCT, { colour: "black", size: "m" })).toBe(
      "Aurora Classic Tee — Colour: Black, Size: M",
    );
  });

  it("leaves out dimensions that have not been chosen", () => {
    expect(imageAltText(TEST_PRODUCT, {})).toBe("Aurora Classic Tee, no variant selected");
    expect(imageAltText(TEST_PRODUCT, { size: "m" })).toBe("Aurora Classic Tee — Size: M");
  });
});
