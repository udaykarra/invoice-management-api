"""Pydantic v2 schemas for request validation, data serialization, and API responses."""

from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.models import InvoiceStatus


class InvoiceItemCreate(BaseModel):
    """Schema for creating a line item on an invoice."""

    description: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Clear description of the billed item or service",
    )
    quantity: int = Field(
        ...,
        gt=0,
        description="Quantity must be a positive integer greater than zero",
    )
    unit_price: Decimal = Field(
        ...,
        ge=Decimal("0.00"),
        le=Decimal("999999999.99"),
        description="Unit price must be non-negative with up to 2 decimal places",
    )

    @field_validator("unit_price")
    @classmethod
    def validate_decimal_scale(cls, v: Decimal) -> Decimal:
        """Strictly enforce maximum of 2 decimal places on unit_price."""
        if v.as_tuple().exponent < -2:
            raise ValueError("unit_price must have at most 2 decimal places")
        return v

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class InvoiceItemResponse(BaseModel):
    """Schema for a persisted invoice line item."""

    id: int
    description: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal

    model_config = ConfigDict(from_attributes=True)


class InvoiceCreate(BaseModel):
    """Schema for creating a new invoice."""

    customer_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the customer or organization",
    )
    customer_email: str = Field(
        ...,
        pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
        description="Valid customer email address",
    )
    currency: str = Field(
        default="USD",
        min_length=3,
        max_length=3,
        description="ISO 4217 three-letter currency code",
    )
    tax_rate: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        le=Decimal("1.00"),
        description="Tax rate as a decimal percentage between 0.00 (0%) and 1.00 (100%)",
    )
    items: List[InvoiceItemCreate] = Field(
        default_factory=list,
        description="List of invoice line items (can be empty)",
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Optional administrative notes or payment instructions",
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class InvoiceResponse(BaseModel):
    """Schema for returning an invoice with calculated totals and line items."""

    id: str
    customer_name: str
    customer_email: str
    status: InvoiceStatus
    currency: str
    tax_rate: Decimal
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    items: List[InvoiceItemResponse]

    model_config = ConfigDict(from_attributes=True)


class ErrorDetail(BaseModel):
    """Structured detail inside an API error envelope."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    details: Optional[Any] = Field(default=None, description="Supplemental error diagnostics or field errors")


class ErrorResponse(BaseModel):
    """Standardized top-level error response envelope."""

    error: ErrorDetail
