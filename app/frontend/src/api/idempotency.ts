/**
 * Idempotency keys for add-to-cart.
 *
 * A fresh key per logical add. The key is what makes a retry safe, so it must stay the
 * same for the whole lifetime of one request (including any transport-level retry) and
 * must never be reused for a different add.
 */

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // Fallback for environments without Web Crypto (older jsdom, non-secure origins).
  // Still unique enough to keep the header well-formed and the behaviour correct.
  return `key-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
