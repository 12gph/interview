"""Runtime configuration.

Deliberately a module of constants rather than a settings framework. This app has
exactly one deployment shape (single process, in-memory store), and inventing a
configuration layer for one shape is the kind of complexity the brief asks us to
avoid. The two values that genuinely need to vary per environment are read from
the environment.
"""

from __future__ import annotations

import os

APP_NAME = "Variant PDP API"
APP_VERSION = "1.0.0"

# --- Cart limits -------------------------------------------------------------
# Not business rules from the brief. They exist so that a single request cannot
# reserve an absurd amount of stock or grow the cart without bound, which would
# otherwise make the "stock race" behaviour unrepresentative of reality.
MAX_QUANTITY_PER_REQUEST = 100
MAX_CART_LINES = 50

# --- Idempotency -------------------------------------------------------------
IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
IDEMPOTENCY_KEY_MAX_LENGTH = 128

# --- CORS --------------------------------------------------------------------
# Defaults to the Vite dev server. Never "*": this service has no authentication,
# so the origin list is the only thing separating it from any page on the web.
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def cors_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", DEFAULT_CORS_ORIGINS)
    origins = [item.strip() for item in raw.split(",")]
    return [origin for origin in origins if origin]
