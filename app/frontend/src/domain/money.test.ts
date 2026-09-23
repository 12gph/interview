/** Money formatting tests: minor units in, a readable string out. */

import { describe, expect, it } from "vitest";

import { formatMinorUnits } from "./money";

describe("formatMinorUnits", () => {
  it("divides by a hundred exactly once, at the display boundary", () => {
    expect(formatMinorUnits(4900, "USD")).toBe("$49.00");
    expect(formatMinorUnits(5700, "USD")).toBe("$57.00");
  });

  it("keeps the cents", () => {
    expect(formatMinorUnits(1, "USD")).toBe("$0.01");
    expect(formatMinorUnits(1999, "USD")).toBe("$19.99");
  });

  it("handles zero", () => {
    expect(formatMinorUnits(0, "USD")).toBe("$0.00");
  });
});
