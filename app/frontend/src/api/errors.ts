/**
 * The error surface the UI reasons about.
 *
 * Backend codes are carried through unchanged. Mapping them all to "something went
 * wrong" would throw away the difference between "we asked for too many" and "the
 * server is down" -- two cases that need different wording and different retry
 * affordances.
 */

export type ApiErrorCode =
  | "VALIDATION_ERROR"
  | "PRODUCT_NOT_FOUND"
  | "SKU_NOT_FOUND"
  | "INSUFFICIENT_STOCK"
  | "IDEMPOTENCY_KEY_CONFLICT"
  | "NOT_FOUND"
  | "INTERNAL_ERROR"
  // Client-side only: the request never produced a response.
  | "NETWORK_ERROR"
  | "TIMEOUT";

export interface ApiErrorDetails {
  readonly skuId?: string;
  readonly requested?: number;
  readonly available?: number;
  readonly field?: string;
  readonly reason?: string;
}

export class ApiRequestError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number;
  readonly details: ApiErrorDetails;

  constructor(
    code: ApiErrorCode,
    message: string,
    status: number,
    details: ApiErrorDetails = {},
  ) {
    super(message);
    this.name = "ApiRequestError";
    this.code = code;
    this.status = status;
    this.details = details;
  }

  /** Whether retrying the identical request could plausibly succeed. */
  get isRetryable(): boolean {
    return this.code === "NETWORK_ERROR" || this.code === "TIMEOUT" || this.status >= 500;
  }
}

/** Normalise anything thrown by the client into an ApiRequestError. */
export function toApiRequestError(error: unknown): ApiRequestError {
  if (error instanceof ApiRequestError) {
    return error;
  }
  const message = error instanceof Error ? error.message : "Unknown failure.";
  return new ApiRequestError("NETWORK_ERROR", message, 0);
}
