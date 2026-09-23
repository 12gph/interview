/**
 * The only module that talks HTTP.
 *
 * Its job: build the URL, attach the idempotency key, apply a timeout, translate
 * wire -> domain, and collapse every failure mode into one `ApiRequestError`. Components
 * never see a `Response`, a status code, or a snake_case field.
 *
 * The wire shapes are asserted rather than schema-validated at runtime. Both sides ship
 * from this one repository and the same commit, so a validation library would add a
 * dependency and a second source of truth for a mismatch that cannot happen in
 * practice; the backend's own tests are what pin the shape down.
 */

import type {
  AddToCartResult,
  Cart,
  CartLine,
  OptionDimension,
  OptionValue,
  Product,
  Sku,
  SkuAvailability,
} from "../domain/types";
import { ApiRequestError } from "./errors";
import type { ApiErrorCode, ApiErrorDetails } from "./errors";
import type {
  WireAddToCartResponse,
  WireCart,
  WireCartLine,
  WireErrorResponse,
  WireOptionDimension,
  WireOptionValue,
  WireProduct,
  WireSku,
  WireSkuAvailability,
} from "./types";

const DEFAULT_BASE_URL = "http://localhost:8000";
const DEFAULT_TIMEOUT_MS = 8000;

const KNOWN_ERROR_CODES: readonly string[] = [
  "VALIDATION_ERROR",
  "PRODUCT_NOT_FOUND",
  "SKU_NOT_FOUND",
  "INSUFFICIENT_STOCK",
  "IDEMPOTENCY_KEY_CONFLICT",
  "NOT_FOUND",
  "INTERNAL_ERROR",
];

export interface AddToCartInput {
  readonly skuId: string;
  readonly quantity: number;
  /** Stable for the lifetime of one logical add; a new one for each new add. */
  readonly idempotencyKey: string;
}

export interface ApiClient {
  getProduct(productId: string): Promise<Product>;
  getCart(): Promise<Cart>;
  addToCart(input: AddToCartInput): Promise<AddToCartResult>;
}

export interface ApiClientOptions {
  /** Defaults to VITE_API_BASE_URL, then http://localhost:8000. */
  readonly baseUrl?: string;
  /** Injectable so tests can drive the network without a server. */
  readonly fetchImpl?: typeof globalThis.fetch;
  readonly timeoutMs?: number;
}

interface SendOptions {
  readonly method: "GET" | "POST";
  readonly body?: unknown;
  readonly headers?: Record<string, string>;
}

function resolveBaseUrl(override?: string): string {
  if (override !== undefined) {
    return override.replace(/\/+$/, "");
  }
  const fromEnv = import.meta.env.VITE_API_BASE_URL;
  return (fromEnv ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
}

function isKnownErrorCode(code: string): code is ApiErrorCode {
  return KNOWN_ERROR_CODES.some((known) => known === code);
}

function toApiErrorDetails(raw: unknown): ApiErrorDetails {
  const details: {
    skuId?: string;
    requested?: number;
    available?: number;
    field?: string;
    reason?: string;
  } = {};

  if (typeof raw !== "object" || raw === null) {
    return details;
  }
  const record = raw as Record<string, unknown>;

  // Each field is copied only when it really is present, so `exactOptionalPropertyTypes`
  // is satisfied and `undefined` never masquerades as a value.
  if (typeof record.sku_id === "string") details.skuId = record.sku_id;
  if (typeof record.requested === "number") details.requested = record.requested;
  if (typeof record.available === "number") details.available = record.available;
  if (typeof record.field === "string") details.field = record.field;
  if (typeof record.reason === "string") details.reason = record.reason;

  return details;
}

function errorFromResponse(status: number, payload: unknown): ApiRequestError {
  const wire = payload as Partial<WireErrorResponse> | null;
  const body = wire?.error;

  if (body !== undefined && typeof body.code === "string" && isKnownErrorCode(body.code)) {
    return new ApiRequestError(body.code, body.message, status, toApiErrorDetails(body.details));
  }

  return new ApiRequestError(
    status >= 500 ? "INTERNAL_ERROR" : "VALIDATION_ERROR",
    `The request failed with status ${status}.`,
    status,
  );
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (text === "") {
    return null;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

function toOptionValue(wire: WireOptionValue): OptionValue {
  return { value: wire.value, label: wire.label, swatch: wire.swatch };
}

function toOptionDimension(wire: WireOptionDimension): OptionDimension {
  return {
    key: wire.key,
    label: wire.label,
    values: wire.values.map(toOptionValue),
  };
}

function toSku(wire: WireSku): Sku {
  return {
    id: wire.id,
    options: { ...wire.options },
    priceMinor: wire.price_minor,
    currency: wire.currency,
    availableQuantity: wire.available_quantity,
    inStock: wire.in_stock,
    imageUrl: wire.image_url,
  };
}

function toProduct(wire: WireProduct): Product {
  return {
    id: wire.id,
    name: wire.name,
    description: wire.description,
    currency: wire.currency,
    heroImageUrl: wire.hero_image_url,
    optionDimensions: wire.option_dimensions.map(toOptionDimension),
    skus: wire.skus.map(toSku),
  };
}

function toCartLine(wire: WireCartLine): CartLine {
  return {
    skuId: wire.sku_id,
    quantity: wire.quantity,
    unitPriceMinor: wire.unit_price_minor,
    lineTotalMinor: wire.line_total_minor,
    name: wire.name,
    imageUrl: wire.image_url,
    options: { ...wire.options },
  };
}

function toCart(wire: WireCart): Cart {
  return {
    id: wire.id,
    currency: wire.currency,
    items: wire.items.map(toCartLine),
    totalItemCount: wire.total_item_count,
    subtotalMinor: wire.subtotal_minor,
  };
}

function toAvailability(wire: WireSkuAvailability): SkuAvailability {
  return { skuId: wire.sku_id, availableQuantity: wire.available_quantity };
}

export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const baseUrl = resolveBaseUrl(options.baseUrl);
  const fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  async function send(
    path: string,
    sendOptions: SendOptions,
  ): Promise<{ response: Response; payload: unknown }> {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      controller.abort();
    }, timeoutMs);

    let response: Response;
    try {
      response = await fetchImpl(`${baseUrl}${path}`, {
        method: sendOptions.method,
        headers: {
          Accept: "application/json",
          ...(sendOptions.body === undefined ? {} : { "Content-Type": "application/json" }),
          ...(sendOptions.headers ?? {}),
        },
        ...(sendOptions.body === undefined ? {} : { body: JSON.stringify(sendOptions.body) }),
        signal: controller.signal,
      });
    } catch (error) {
      // Only our own timer aborts these requests, so an abort is always a timeout.
      if (controller.signal.aborted) {
        throw new ApiRequestError("TIMEOUT", "The request timed out.", 0);
      }
      const reason = error instanceof Error ? error.message : "The request could not be sent.";
      throw new ApiRequestError("NETWORK_ERROR", reason, 0);
    } finally {
      clearTimeout(timer);
    }

    const payload = await readJson(response);
    if (!response.ok) {
      throw errorFromResponse(response.status, payload);
    }
    return { response, payload };
  }

  return {
    async getProduct(productId: string): Promise<Product> {
      const { payload } = await send(`/api/products/${encodeURIComponent(productId)}`, {
        method: "GET",
      });
      return toProduct(payload as WireProduct);
    },

    async getCart(): Promise<Cart> {
      const { payload } = await send("/api/cart", { method: "GET" });
      return toCart(payload as WireCart);
    },

    async addToCart(input: AddToCartInput): Promise<AddToCartResult> {
      const { response, payload } = await send("/api/cart/items", {
        method: "POST",
        // snake_case here on purpose: this is the wire body, and keeping it visibly
        // different from the domain model is what stops a domain field leaking out.
        body: { sku_id: input.skuId, quantity: input.quantity },
        headers: { "Idempotency-Key": input.idempotencyKey },
      });

      const wire = payload as WireAddToCartResponse;
      return {
        cart: toCart(wire.cart),
        availability: toAvailability(wire.sku_availability),
        replayed: response.headers.get("Idempotency-Replayed") === "true",
      };
    },
  };
}
