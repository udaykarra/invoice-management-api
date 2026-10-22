"""FastAPI application entry point for the Invoice Management API."""

from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, Depends, Header, Query, Response, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.database import Base, engine, get_db
from app.errors import (
    AppException,
    BadRequestException,
    EntityNotFoundException,
    app_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.models import InvoiceStatus
from app.schemas import (
    ErrorResponse,
    InvoiceCreate,
    InvoiceResponse,
)
import app.crud as crud


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown routines."""
    # Ensure tables are created on startup (e.g. for development / in-memory SQLite)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Production-grade Invoice Management API demonstrating TDD, idempotency, transaction safety, and exact arithmetic.",
    lifespan=lifespan,
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request"},
        404: {"model": ErrorResponse, "description": "Resource Not Found"},
        409: {"model": ErrorResponse, "description": "Conflict / Idempotency Violation"},
        422: {"model": ErrorResponse, "description": "Unprocessable Entity / Schema Validation Error"},
    },
)

# Register custom exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


@app.get("/health", tags=["System"], summary="Health check endpoint")
def health_check():
    """Verify service readiness and active version."""
    return {"status": "healthy", "version": settings.APP_VERSION}


@app.post(
    "/invoices/",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Invoices"],
    summary="Create a new invoice",
    responses={
        200: {"model": InvoiceResponse, "description": "Idempotent replay of previously created invoice"},
        201: {"model": InvoiceResponse, "description": "Newly created invoice"},
    },
)
def create_invoice_endpoint(
    invoice_in: InvoiceCreate,
    response: Response,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    """Create an invoice with ACID transactional guarantees and optional idempotency key.

    If an `Idempotency-Key` is provided:
    - First submission: Creates the invoice and returns HTTP 201 Created.
    - Subsequent identical submissions: Returns the cached invoice with HTTP 200 OK.
    - Subsequent differing submissions: Returns HTTP 409 Conflict.
    """
    if idempotency_key is not None:
        if not idempotency_key.strip():
            raise BadRequestException("Idempotency-Key header cannot be empty or contain only whitespace.")

    invoice, is_new = crud.create_invoice(
        db=db,
        invoice_in=invoice_in,
        idempotency_key=idempotency_key,
    )
    if not is_new:
        response.status_code = status.HTTP_200_OK
        response.headers["X-Idempotent-Replay"] = "true"
    return invoice


@app.get(
    "/invoices/",
    response_model=List[InvoiceResponse],
    tags=["Invoices"],
    summary="List invoices",
)
def list_invoices_endpoint(
    skip: int = Query(0, ge=0, description="Offset pagination skip count"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum items per page"),
    status: Optional[InvoiceStatus] = Query(None, description="Filter by invoice status"),
    db: Session = Depends(get_db),
):
    """Retrieve a paginated list of invoices with optional status filtering."""
    return crud.list_invoices(db=db, skip=skip, limit=limit, status=status)


@app.get(
    "/invoices/{invoice_id}",
    response_model=InvoiceResponse,
    tags=["Invoices"],
    summary="Get invoice details",
)
def get_invoice_endpoint(
    invoice_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve complete invoice details including line items."""
    invoice = crud.get_invoice(db=db, invoice_id=invoice_id)
    if not invoice:
        raise EntityNotFoundException(resource="Invoice", identifier=invoice_id)
    return invoice


@app.post(
    "/invoices/{invoice_id}/pay",
    response_model=InvoiceResponse,
    tags=["Invoices"],
    summary="Mark invoice as paid",
)
def pay_invoice_endpoint(
    invoice_id: str,
    db: Session = Depends(get_db),
):
    """Transition invoice lifecycle status to PAID. Rejects cancelled invoices with HTTP 409."""
    return crud.pay_invoice(db=db, invoice_id=invoice_id)


@app.post(
    "/invoices/{invoice_id}/cancel",
    response_model=InvoiceResponse,
    tags=["Invoices"],
    summary="Cancel invoice",
)
def cancel_invoice_endpoint(
    invoice_id: str,
    db: Session = Depends(get_db),
):
    """Transition invoice lifecycle status to CANCELLED. Rejects paid invoices with HTTP 409."""
    return crud.cancel_invoice(db=db, invoice_id=invoice_id)
