"""CRUD operations, exact financial arithmetic, idempotency logic, and ACID transaction safety."""

import hashlib
import json
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from app.errors import (
    EntityNotFoundException,
    IdempotencyConflictException,
    InvalidStateTransitionException,
)
from app.models import IdempotencyRecord, Invoice, InvoiceItem, InvoiceStatus
from app.schemas import InvoiceCreate, InvoiceResponse

TWO_PLACES = Decimal("0.01")


def round_currency(value: Decimal) -> Decimal:
    """Round currency deterministically using standard commercial ROUND_HALF_UP.

    Avoids floating-point drift and binary representation errors.
    """
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def calculate_line_total(quantity: int, unit_price: Decimal) -> Decimal:
    """Calculate line item total: quantity * unit_price rounded to 2 decimal places."""
    return round_currency(Decimal(quantity) * unit_price)


def calculate_invoice_totals(
    items: List[any],
    tax_rate: Decimal,
) -> Tuple[Decimal, Decimal, Decimal]:
    """Calculate subtotal, tax amount, and grand total using exact Decimal arithmetic.

    Handles zero values, fractional cents, and empty line item lists gracefully.
    """
    subtotal = Decimal("0.00")
    for item in items:
        line_total = calculate_line_total(item.quantity, item.unit_price)
        subtotal += line_total

    subtotal = round_currency(subtotal)
    tax_amount = round_currency(subtotal * tax_rate)
    total_amount = round_currency(subtotal + tax_amount)
    return subtotal, tax_amount, total_amount


def compute_payload_hash(payload_dict: dict) -> str:
    """Generate deterministic SHA-256 hash of canonicalized JSON request payload."""
    canonical_json = json.dumps(payload_dict, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def get_invoice(db: Session, invoice_id: str) -> Optional[Invoice]:
    """Retrieve an invoice by unique ID with eager-loaded items."""
    return db.query(Invoice).filter(Invoice.id == invoice_id).first()


def list_invoices(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status: Optional[InvoiceStatus] = None,
) -> List[Invoice]:
    """List invoices with pagination and optional status filter."""
    query = db.query(Invoice)
    if status is not None:
        query = query.filter(Invoice.status == status)
    return query.order_by(Invoice.created_at.desc()).offset(skip).limit(limit).all()


def create_invoice(
    db: Session,
    invoice_in: InvoiceCreate,
    idempotency_key: Optional[str] = None,
) -> Tuple[Invoice, bool]:
    """Create a new invoice atomically.

    Guarantees:
    - ACID Transaction: If any step fails, entire transaction is rolled back.
    - Idempotency: Replaying with identical key returns cached invoice (is_new=False).
    - Conflict Detection: Replaying key with differing payload raises 409 Conflict.
    - Exact Arithmetic: All totals calculated with Decimal ROUND_HALF_UP.

    Returns:
        Tuple of (invoice, is_new: bool)
    """
    payload_dict = invoice_in.model_dump(mode="json")
    payload_hash = compute_payload_hash(payload_dict)

    if idempotency_key:
        cleaned_key = idempotency_key.strip()
        existing_rec = db.query(IdempotencyRecord).filter(IdempotencyRecord.key == cleaned_key).first()
        if existing_rec:
            if existing_rec.request_hash == payload_hash:
                # Payload matches: replay idempotent response
                cached_data = json.loads(existing_rec.response_body)
                cached_invoice = get_invoice(db, cached_data["id"])
                if cached_invoice:
                    return cached_invoice, False
            else:
                # Key reused with differing payload: reject with 409 Conflict
                raise IdempotencyConflictException(cleaned_key)

    try:
        invoice_id = f"inv_{uuid.uuid4().hex[:12]}"
        subtotal, tax_amount, total_amount = calculate_invoice_totals(invoice_in.items, invoice_in.tax_rate)

        db_invoice = Invoice(
            id=invoice_id,
            customer_name=invoice_in.customer_name,
            customer_email=invoice_in.customer_email,
            status=InvoiceStatus.ISSUED,
            currency=invoice_in.currency.upper(),
            tax_rate=invoice_in.tax_rate,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total_amount=total_amount,
            notes=invoice_in.notes,
        )
        db.add(db_invoice)
        db.flush()

        for item_in in invoice_in.items:
            line_total = calculate_line_total(item_in.quantity, item_in.unit_price)
            db_item = InvoiceItem(
                invoice_id=db_invoice.id,
                description=item_in.description,
                quantity=item_in.quantity,
                unit_price=item_in.unit_price,
                line_total=line_total,
            )
            db.add(db_item)

        db.flush()

        if idempotency_key:
            response_schema = InvoiceResponse.model_validate(db_invoice)
            idem_record = IdempotencyRecord(
                key=idempotency_key.strip(),
                request_path="/invoices/",
                request_hash=payload_hash,
                response_code=201,
                response_body=response_schema.model_dump_json(),
            )
            db.add(idem_record)

        db.commit()
        db.refresh(db_invoice)
        return db_invoice, True

    except Exception:
        db.rollback()
        raise


def pay_invoice(db: Session, invoice_id: str) -> Invoice:
    """Transition an invoice to PAID status."""
    invoice = get_invoice(db, invoice_id)
    if not invoice:
        raise EntityNotFoundException(resource="Invoice", identifier=invoice_id)

    if invoice.status == InvoiceStatus.PAID:
        return invoice  # Idempotent state

    if invoice.status == InvoiceStatus.CANCELLED:
        raise InvalidStateTransitionException(
            current_status=invoice.status.value,
            target_status=InvoiceStatus.PAID.value,
        )

    try:
        invoice.status = InvoiceStatus.PAID
        db.commit()
        db.refresh(invoice)
        return invoice
    except Exception:
        db.rollback()
        raise


def cancel_invoice(db: Session, invoice_id: str) -> Invoice:
    """Transition an invoice to CANCELLED status."""
    invoice = get_invoice(db, invoice_id)
    if not invoice:
        raise EntityNotFoundException(resource="Invoice", identifier=invoice_id)

    if invoice.status == InvoiceStatus.CANCELLED:
        return invoice  # Idempotent state

    if invoice.status == InvoiceStatus.PAID:
        raise InvalidStateTransitionException(
            current_status=invoice.status.value,
            target_status=InvoiceStatus.CANCELLED.value,
        )

    try:
        invoice.status = InvoiceStatus.CANCELLED
        db.commit()
        db.refresh(invoice)
        return invoice
    except Exception:
        db.rollback()
        raise
