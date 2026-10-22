"""Standardized API exception hierarchy and FastAPI exception handlers."""

from typing import Any, Optional
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppException(Exception):
    """Base application exception with HTTP status mapping and machine-readable error codes."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[Any] = None,
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


class EntityNotFoundException(AppException):
    """Raised when a requested resource does not exist (HTTP 404)."""

    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            status_code=404,
            code="RESOURCE_NOT_FOUND",
            message=f"{resource} with identifier '{identifier}' was not found.",
        )


class IdempotencyConflictException(AppException):
    """Raised when an Idempotency-Key is reused with a different request payload (HTTP 409)."""

    def __init__(self, key: str):
        super().__init__(
            status_code=409,
            code="IDEMPOTENCY_CONFLICT",
            message=f"Idempotency-Key '{key}' was previously used with a different request payload.",
        )


class InvalidStateTransitionException(AppException):
    """Raised when an operation violates state lifecycle rules (HTTP 409)."""

    def __init__(self, current_status: str, target_status: str):
        super().__init__(
            status_code=409,
            code="INVALID_STATE_TRANSITION",
            message=f"Cannot transition invoice from '{current_status}' to '{target_status}'.",
        )


class BadRequestException(AppException):
    """Raised for general malformed or illegal client requests (HTTP 400)."""

    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(
            status_code=400,
            code="BAD_REQUEST",
            message=message,
            details=details,
        )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Format custom domain exceptions into standard error envelopes."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Format Pydantic schema validation failures into standard error envelopes (HTTP 422)."""
    # Clean up error details for JSON serialization
    details = []
    for error in exc.errors():
        details.append(
            {
                "field": ".".join(str(loc) for loc in error.get("loc", [])),
                "type": error.get("type"),
                "message": error.get("msg"),
            }
        )

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "The request payload failed schema validation.",
                "details": details,
            }
        },
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Format standard Starlette HTTPExceptions into the unified envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "HTTP_ERROR",
                "message": exc.detail if isinstance(exc.detail, str) else "HTTP request error",
                "details": None,
            }
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Fallback handler for unhandled server exceptions (HTTP 500)."""
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected server error occurred. Please contact support.",
                "details": None,
            }
        },
    )
