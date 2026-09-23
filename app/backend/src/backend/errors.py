"""Structured error model.

Every failure the API can produce leaves through this module, so the shape of an
error response is defined in exactly one place. The alternative -- letting
FastAPI's default 422 envelope, the ``HTTPException`` envelope and hand-rolled
``JSONResponse`` bodies coexist -- would make the contract impossible to document
in the README without listing exceptions.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .middleware import REQUEST_ID_HEADER, request_id_of

logger = logging.getLogger(__name__)


class ErrorCode:
    """Codes published in the README.

    Clients branch on these values, never on the human-readable message.
    """

    VALIDATION_ERROR = "VALIDATION_ERROR"
    PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
    SKU_NOT_FOUND = "SKU_NOT_FOUND"
    INSUFFICIENT_STOCK = "INSUFFICIENT_STOCK"
    IDEMPOTENCY_KEY_CONFLICT = "IDEMPOTENCY_KEY_CONFLICT"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"


def build_error_payload(
    code: str,
    message: str,
    details: dict[str, Any],
    request_id: str,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id,
        }
    }


class ApiError(Exception):
    """Base class for failures that map to a documented status code and error code."""

    status_code: int = 500
    code: str = ErrorCode.INTERNAL_ERROR

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = dict(details or {})

    def to_payload(self, request_id: str) -> dict[str, Any]:
        return build_error_payload(self.code, self.message, self.details, request_id)


class ValidationError(ApiError):
    """Request is syntactically or semantically unacceptable for our own rules."""

    status_code = 400
    code = ErrorCode.VALIDATION_ERROR


class ProductNotFound(ApiError):
    status_code = 404
    code = ErrorCode.PRODUCT_NOT_FOUND

    def __init__(self, product_id: str) -> None:
        super().__init__(
            f"Product {product_id!r} does not exist.",
            details={"product_id": product_id},
        )


class SkuNotFound(ApiError):
    status_code = 404
    code = ErrorCode.SKU_NOT_FOUND

    def __init__(self, sku_id: str) -> None:
        super().__init__(
            f"SKU {sku_id!r} does not exist on this product.",
            details={"sku_id": sku_id},
        )


class InsufficientStock(ApiError):
    status_code = 409
    code = ErrorCode.INSUFFICIENT_STOCK

    def __init__(self, sku_id: str, requested: int, available: int) -> None:
        super().__init__(
            f"Only {available} unit(s) of {sku_id} are available.",
            # `available` is exposed on purpose: it lets the client correct its own
            # stale stock figure without a second round trip. See the README.
            details={"sku_id": sku_id, "requested": requested, "available": available},
        )


class IdempotencyKeyConflict(ApiError):
    """Same Idempotency-Key, different request body.

    Returning the first response here would silently hide a client bug, so this is
    reported as a conflict instead.
    """

    status_code = 409
    code = ErrorCode.IDEMPOTENCY_KEY_CONFLICT

    def __init__(self, idempotency_key: str) -> None:
        super().__init__(
            "This Idempotency-Key was already used with a different request body.",
            details={"idempotency_key": idempotency_key},
        )


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    request_id = request_id_of(request)
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_payload(request_id),
        # Set on the response as well as by the middleware: a failure raised while
        # the middleware stack unwinds would otherwise reach the client unstamped.
        headers={REQUEST_ID_HEADER: request_id},
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Re-shape FastAPI's default 422 into our 400 envelope.

    Pydantic rejects `extra` fields (see `AddCartItemRequest`), so a client that
    tries to send its own price or stock lands here rather than being silently
    ignored. Keeping that on 400 alongside our other input errors means a client
    only ever has to handle one error shape.
    """
    fields = [
        {
            "field": ".".join(str(part) for part in error.get("loc", ()) if part != "body"),
            "reason": str(error.get("msg", "")),
        }
        for error in exc.errors()
    ]
    first = fields[0] if fields else {"field": "body", "reason": "invalid request body"}
    request_id = request_id_of(request)
    payload = build_error_payload(
        ErrorCode.VALIDATION_ERROR,
        f"Invalid request: {first['field'] or 'body'} -- {first['reason']}.",
        {"fields": fields},
        request_id,
    )
    return JSONResponse(status_code=400, content=payload, headers={REQUEST_ID_HEADER: request_id})


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Give framework-raised HTTP errors (e.g. unknown route) the same envelope."""
    code = ErrorCode.NOT_FOUND if exc.status_code == 404 else ErrorCode.INTERNAL_ERROR
    request_id = request_id_of(request)
    payload = build_error_payload(code, str(exc.detail), {}, request_id)
    return JSONResponse(
        status_code=exc.status_code,
        content=payload,
        headers={REQUEST_ID_HEADER: request_id},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last line of defence.

    The exception detail goes to the log, never to the client: an unexpected
    failure is exactly the case where a stack trace would leak internals.
    """
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    request_id = request_id_of(request)
    payload = build_error_payload(
        ErrorCode.INTERNAL_ERROR,
        "An unexpected error occurred.",
        {},
        request_id,
    )
    return JSONResponse(status_code=500, content=payload, headers={REQUEST_ID_HEADER: request_id})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
