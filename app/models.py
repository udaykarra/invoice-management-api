"""SQLAlchemy ORM models representing Invoices, Line Items, and Idempotency Records."""

import enum
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Numeric,
    Text,
    DateTime,
    ForeignKey,
    Enum as SqlEnum,
)
from sqlalchemy.orm import relationship
from app.database import Base


class InvoiceStatus(str, enum.Enum):
    """Lifecycle statuses of an invoice."""

    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class Invoice(Base):
    """Invoice entity representing a billing record."""

    __tablename__ = "invoices"

    id = Column(String(36), primary_key=True, index=True)
    customer_name = Column(String(255), nullable=False)
    customer_email = Column(String(255), nullable=False)
    status = Column(
        SqlEnum(InvoiceStatus, name="invoice_status_enum", native_enum=False),
        nullable=False,
        default=InvoiceStatus.ISSUED,
    )
    currency = Column(String(3), nullable=False, default="USD")
    tax_rate = Column(Numeric(precision=5, scale=4, asdecimal=True), nullable=False, default=0)
    subtotal = Column(Numeric(precision=12, scale=2, asdecimal=True), nullable=False, default=0)
    tax_amount = Column(Numeric(precision=12, scale=2, asdecimal=True), nullable=False, default=0)
    total_amount = Column(Numeric(precision=12, scale=2, asdecimal=True), nullable=False, default=0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    items = relationship(
        "InvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceItem.id",
        lazy="joined",
    )


class InvoiceItem(Base):
    """Line item belonging to an invoice."""

    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(
        String(36),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(precision=12, scale=2, asdecimal=True), nullable=False)
    line_total = Column(Numeric(precision=12, scale=2, asdecimal=True), nullable=False)

    # Relationships
    invoice = relationship("Invoice", back_populates="items")


class IdempotencyRecord(Base):
    """Audit table for idempotency keys to guarantee at-most-once mutation semantics."""

    __tablename__ = "idempotency_records"

    key = Column(String(128), primary_key=True, index=True)
    request_path = Column(String(255), nullable=False)
    request_hash = Column(String(64), nullable=False)
    response_code = Column(Integer, nullable=False)
    response_body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
