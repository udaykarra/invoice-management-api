"""CRUD operations, exact financial arithmetic, idempotency logic, and ACID transaction safety."""

import hashlib
import json
import random
import time
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional, Sequence, Tuple, Union

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.errors import (
    DatabaseBusyException,
    EntityNotFoundException,
    IdempotencyConflictException,
    InvalidStateTransitionException,
)
from app.models import IdempotencyRecord, Invoice, InvoiceItem, InvoiceStatus
from app.schemas import InvoiceCreate, InvoiceItemCreate, InvoiceResponse

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
    items: Sequence[Union[InvoiceItemCreate, InvoiceItem]],
    tax_rate: Decimal,
) -> Tuple[Decimal, Decimal, Decimal]:
    """Calculate subtotal, tax amount, and grand total using exact Decimal arithmetic.

    Handles zero values, fractional cents, and empty line item lists gracefully.
    """
    subtotal = Decimal("0.00")
    for item in items:
        line_total = calculate_line_total(int(item.quantity), Decimal(str(item.unit_price)))
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
) -> Tuple[Union[Invoice, InvoiceResponse], bool, int]:
    """Create a new invoice atomically.

    Guarantees:
    - ACID Transaction: If any step fails, entire transaction is rolled back.
    - Idempotency: Replaying with identical key returns cached original response snapshot (is_new=False).
    - Conflict Detection: Replaying key with differing payload raises 409 Conflict.
    - Exact Arithmetic: All totals calculated with Decimal ROUND_HALF_UP.
    - Concurrency Safety: Bounded retries with exponential backoff & jitter handle SQLite locks.

    Returns:
        Tuple of (invoice_or_response, is_new: bool, response_code: int)
    """
    payload_dict = invoice_in.model_dump(mode="json")
    payload_hash = compute_payload_hash(payload_dict)
    cleaned_key = idempotency_key.strip() if idempotency_key else None

    if cleaned_key:
        existing_rec = db.query(IdempotencyRecord).filter(IdempotencyRecord.key == cleaned_key).first()
        if existing_rec:
            if existing_rec.request_hash == payload_hash:
                # Payload matches: replay exact original response snapshot
                cached_response = InvoiceResponse.model_validate_json(str(existing_rec.response_body))
                orig_code = int(existing_rec.response_code) if existing_rec.response_code else 201
                return cached_response, False, orig_code
            else:
                # Key reused with differing payload: reject with 409 Conflict
                raise IdempotencyConflictException(cleaned_key)

    max_tx_attempts = 5
    for tx_attempt in range(max_tx_attempts):
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

            if cleaned_key:
                response_schema = InvoiceResponse.model_validate(db_invoice)
                idem_record = IdempotencyRecord(
                    key=cleaned_key,
                    request_path="/invoices/",
                    request_hash=payload_hash,
                    response_code=201,
                    response_body=response_schema.model_dump_json(),
                )
                db.add(idem_record)

            db.commit()
            return db_invoice, True, 201

        except (IntegrityError, OperationalError) as exc:
            db.rollback()

            # Handle concurrent race condition where another thread committed this idempotency key
            if cleaned_key:
                max_poll_retries = 15
                base_delay = 0.01  # 10ms
                max_delay = 0.25   # 250ms
                for attempt in range(max_poll_retries):
                    delay = min(max_delay, base_delay * (1.5 ** attempt)) + random.uniform(0.001, 0.015)
                    time.sleep(delay)
                    try:
                        winner_rec = db.query(IdempotencyRecord).filter(IdempotencyRecord.key == cleaned_key).first()
                        if winner_rec:
                            if winner_rec.request_hash == payload_hash:
                                cached_response = InvoiceResponse.model_validate_json(str(winner_rec.response_body))
                                orig_code = int(winner_rec.response_code) if winner_rec.response_code else 201
                                return cached_response, False, orig_code
                            else:
                                raise IdempotencyConflictException(cleaned_key)
                    except OperationalError:
                        continue

            # If OperationalError (database lock) and transaction attempts remain, backoff and retry
            if isinstance(exc, OperationalError):
                if tx_attempt < max_tx_attempts - 1:
                    backoff = min(0.3, 0.02 * (2 ** tx_attempt)) + random.uniform(0.005, 0.025)
                    time.sleep(backoff)
                    continue
                raise DatabaseBusyException("Database lock contention exceeded maximum retry threshold.") from exc

            # Otherwise, unresolvable IntegrityError -> re-raise
            raise

        except Exception:
            db.rollback()
            raise

    raise DatabaseBusyException("Failed to complete invoice creation after maximum transaction retries.")


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
        invoice.status = InvoiceStatus.PAID  # type: ignore[assignment]
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
        invoice.status = InvoiceStatus.CANCELLED  # type: ignore[assignment]
        db.commit()
        db.refresh(invoice)
        return invoice
    except Exception:
        db.rollback()
        raise
