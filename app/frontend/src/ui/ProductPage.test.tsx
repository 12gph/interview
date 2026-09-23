/**
 * Integration tests for the product detail page.
 *
 * These sit at the component boundary on purpose: each one is a behaviour a shopper
 * would notice, and each one fails when the wiring between layers is wrong even if every
 * pure function passes its own unit test. The API client is injected, so nothing here
 * touches the network.
 */

import type { UserEvent } from "@testing-library/user-event";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { ApiClient } from "../api/client";
import { ApiRequestError } from "../api/errors";
import { addResult, fakeClient, TEST_PRODUCT } from "../testing/fixtures";
import { ProductPage } from "./ProductPage";

function renderPage(client: ApiClient = fakeClient()): UserEvent {
  render(<ProductPage client={client} productId={TEST_PRODUCT.id} />);
  return userEvent.setup();
}

async function findProduct(): Promise<void> {
  await screen.findByRole("heading", { name: TEST_PRODUCT.name });
}

/**
 * Locate one option value.
 *
 * Scoped to its own dimension because two groups can share a label prefix ("S" and
 * "Sand"), and matched by prefix rather than exact string because a value's accessible
 * name carries its availability note ("S Out of stock").
 */
function optionRadio(dimension: string, value: string): HTMLElement {
  const group = screen.getByRole("group", { name: dimension });
  return within(group).getByRole("radio", { name: new RegExp(`^${value}(\\s|$)`) });
}

async function choose(user: UserEvent, colour: string, size: string): Promise<void> {
  await user.click(optionRadio("Colour", colour));
  await user.click(optionRadio("Size", size));
}

function quantityField(): HTMLElement {
  return screen.getByLabelText("Quantity");
}

function addButton(): HTMLElement {
  return screen.getByRole("button", { name: "Add to cart" });
}

describe("variant resolution", () => {
  it("keeps price, image and stock in step with the selection", async () => {
    const user = renderPage();
    await findProduct();

    // Nothing chosen yet: the price slot names what is missing rather than showing a
    // number for a variant nobody picked.
    expect(screen.getByText("Select Colour and Size")).toBeInTheDocument();
    expect(screen.getByRole("img")).toHaveAttribute("src", TEST_PRODUCT.heroImageUrl);

    await choose(user, "Black", "M");

    expect(screen.getByText("$49.00")).toBeInTheDocument();
    expect(screen.getByRole("img")).toHaveAttribute("src", "/images/tee-black-m.svg");
    // The alt text has to name the variant; "product image" would help nobody.
    expect(screen.getByRole("img")).toHaveAccessibleName(
      "Aurora Classic Tee — Colour: Black, Size: M",
    );

    // Changing only the colour has to move the price and the image with it.
    await user.click(optionRadio("Colour", "Sage"));
    expect(screen.getByText("$57.00")).toBeInTheDocument();
    expect(screen.getByRole("img")).toHaveAttribute("src", "/images/tee-sage-m.svg");

    // Sand/S exists but has no units left: it stays selectable, its price still shows,
    // and the refusal is the button's job.
    await user.click(optionRadio("Colour", "Sand"));
    await user.click(optionRadio("Size", "S"));
    expect(screen.getByText("$53.00")).toBeInTheDocument();
    expect(screen.getAllByText("Out of stock").length).toBeGreaterThanOrEqual(1);
    expect(addButton()).toBeDisabled();
  });

  it("disables the combinations the catalog does not make", async () => {
    const user = renderPage();
    await findProduct();

    // With no colour chosen every size is still reachable.
    expect(optionRadio("Size", "L")).toBeEnabled();

    // Black is made in S and M only, so L must become unselectable.
    await user.click(optionRadio("Colour", "Black"));
    expect(optionRadio("Size", "L")).toBeDisabled();
    expect(optionRadio("Size", "M")).toBeEnabled();

    // Sage goes the other way and has no S.
    await user.click(optionRadio("Colour", "Sage"));
    expect(optionRadio("Size", "S")).toBeDisabled();
    expect(optionRadio("Size", "L")).toBeEnabled();
  });
});

describe("add to cart", () => {
  it("sends a single request when the button is clicked twice in one frame", async () => {
    let calls = 0;
    const client = fakeClient({
      addToCart: async (input) => {
        calls += 1;
        await new Promise((resolve) => {
          setTimeout(resolve, 20);
        });
        return addResult(input.skuId, 1);
      },
    });

    const user = renderPage(client);
    await findProduct();
    await choose(user, "Black", "M");

    const button = addButton();

    // Both clicks are dispatched before React re-renders, so the button is still enabled
    // for the second one and the synchronous ref guard is the only thing standing in the
    // way. A `useState` flag alone would let both through.
    await act(async () => {
      fireEvent.click(button);
      fireEvent.click(button);
    });

    expect(calls).toBe(1);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Add to cart" })).toBeEnabled();
    });
  });

  it("brings the quantity down, and says so, when the next variant has less stock", async () => {
    const user = renderPage();
    await findProduct();
    await choose(user, "Sand", "M");

    const increase = screen.getByRole("button", { name: "Increase quantity" });
    for (let step = 0; step < 5; step += 1) {
      await user.click(increase);
    }
    expect(quantityField()).toHaveValue(6);

    // Sage/M has exactly one unit, so the quantity has to follow the switch down.
    await user.click(optionRadio("Colour", "Sage"));

    expect(quantityField()).toHaveValue(1);
    expect(screen.getByRole("status")).toHaveTextContent("Quantity adjusted to 1 — only 1 left.");
  });

  it("adopts the server's stock figure when the add is refused", async () => {
    const client = fakeClient({
      addToCart: () =>
        Promise.reject(
          new ApiRequestError("INSUFFICIENT_STOCK", "Not enough stock available.", 409, {
            skuId: "TEE-BLK-M",
            requested: 2,
            available: 1,
          }),
        ),
    });

    const user = renderPage(client);
    await findProduct();
    await choose(user, "Black", "M");
    await user.click(screen.getByRole("button", { name: "Increase quantity" }));
    expect(quantityField()).toHaveValue(2);

    await user.click(addButton());

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/Only 1 left/);
    });
    // The form is corrected using the number the server sent, so trying again can work.
    expect(quantityField()).toHaveValue(1);
  });
});

describe("loading", () => {
  it("offers a retry that actually re-runs the request", async () => {
    let attempts = 0;
    const client = fakeClient({
      getProduct: () => {
        attempts += 1;
        if (attempts === 1) {
          return Promise.reject(new ApiRequestError("NETWORK_ERROR", "Failed to fetch.", 0));
        }
        return Promise.resolve(TEST_PRODUCT);
      },
    });

    const user = renderPage(client);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/couldn.t load this product/);

    await user.click(screen.getByRole("button", { name: "Retry" }));

    await findProduct();
    expect(attempts).toBe(2);
  });
});
