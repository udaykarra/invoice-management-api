"""Comprehensive test suite verifying financial precision, idempotency, validation, error contracts, and ACID transactions."""

from decimal import Decimal
import pytest
from app.models import Invoice, InvoiceItem, InvoiceStatus
from app.errors import IdempotencyConflictException, InvalidStateTransitionException
import app.crud as crud


# ============================================================================
# Task 1: Calculations & Financial Precision Tests (Decimal, Rounding, Zeroes)
# ============================================================================

def test_invoice_creation_exact_decimal_calculation(client):
    """Test that subtotal, tax, and grand totals avoid floating point precision drift."""
    payload = {
        "customer_name": "Acme Corp",
        "customer_email": "billing@acme.com",
        "currency": "USD",
        "tax_rate": "0.1000",  # 10%
        "items": [
            {"description": "Cloud Server", "quantity": 3, "unit_price": "100.10"},  # 300.30
            {"description": "Storage Disk", "quantity": 7, "unit_price": "0.20"},     # 1.40
            {"description": "Bandwidth GB", "quantity": 100, "unit_price": "0.05"},   # 5.00
        ],
    }
    # Expected subtotal = 300.30 + 1.40 + 5.00 = 306.70
    # Expected tax = 306.70 * 0.10 = 30.67
    # Expected total = 306.70 + 30.67 = 337.37
    response = client.post("/invoices/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert Decimal(str(data["subtotal"])) == Decimal("306.70")
    assert Decimal(str(data["tax_amount"])) == Decimal("30.67")
    assert Decimal(str(data["total_amount"])) == Decimal("337.37")
    assert len(data["items"]) == 3
    assert Decimal(str(data["items"][0]["line_total"])) == Decimal("300.30")
    assert Decimal(str(data["items"][1]["line_total"])) == Decimal("1.40")
    assert Decimal(str(data["items"][2]["line_total"])) == Decimal("5.00")


def test_rounding_half_up_behavior(client):
    """Verify commercial ROUND_HALF_UP rounding on fractional cents."""
    # Subtotal: 10.00, Tax rate: 0.1245 -> 10.00 * 0.1245 = 1.245 -> ROUND_HALF_UP should yield 1.25
    payload = {
        "customer_name": "Rounding Corp",
        "customer_email": "finance@rounding.com",
        "tax_rate": "0.1245",
        "items": [
            {"description": "Widget", "quantity": 1, "unit_price": "10.00"},
        ],
    }
    response = client.post("/invoices/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert Decimal(str(data["subtotal"])) == Decimal("10.00")
    assert Decimal(str(data["tax_amount"])) == Decimal("1.25")
    assert Decimal(str(data["total_amount"])) == Decimal("11.25")


def test_invoice_with_zero_tax(client):
    """Ensure tax calculation functions properly when tax_rate is zero."""
    payload = {
        "customer_name": "Zero Tax LLC",
        "customer_email": "taxfree@zerotax.com",
        "tax_rate": "0.0000",
        "items": [
            {"description": "Tax Exempt Consulting", "quantity": 2, "unit_price": "250.00"}
        ],
    }
    response = client.post("/invoices/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert Decimal(str(data["subtotal"])) == Decimal("500.00")
    assert Decimal(str(data["tax_amount"])) == Decimal("0.00")
    assert Decimal(str(data["total_amount"])) == Decimal("500.00")


def test_invoice_with_empty_line_items(client):
    """Ensure invoices with empty items array evaluate totals to zero without errors."""
    payload = {
        "customer_name": "Empty Invoice Inc",
        "customer_email": "empty@invoice.com",
        "tax_rate": "0.2000",
        "items": [],
    }
    response = client.post("/invoices/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert Decimal(str(data["subtotal"])) == Decimal("0.00")
    assert Decimal(str(data["tax_amount"])) == Decimal("0.00")
    assert Decimal(str(data["total_amount"])) == Decimal("0.00")
    assert data["items"] == []


def test_invoice_with_zero_unit_price(client):
    """Ensure zero-dollar line items (e.g., complimentary services) calculate cleanly."""
    payload = {
        "customer_name": "Free Tier User",
        "customer_email": "free@user.com",
        "tax_rate": "0.1000",
        "items": [
            {"description": "Promotional Free Trial", "quantity": 1, "unit_price": "0.00"}
        ],
    }
    response = client.post("/invoices/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert Decimal(str(data["subtotal"])) == Decimal("0.00")
    assert Decimal(str(data["total_amount"])) == Decimal("0.00")


# ============================================================================
# Task 2: Idempotency Tests (Keys, Replays, Conflicts)
# ============================================================================

def test_idempotency_identical_payload_returns_cached_invoice(client, db_session):
    """Ensure submitting the same Idempotency-Key twice replays the response without duplicate rows."""
    payload = {
        "customer_name": "Stripe Corp",
        "customer_email": "billing@stripe.com",
        "currency": "USD",
        "tax_rate": "0.0500",
        "items": [{"description": "API Subscription", "quantity": 1, "unit_price": "99.00"}],
    }
    headers = {"Idempotency-Key": "req_key_abc_123"}

    # First request: Creates invoice
    res1 = client.post("/invoices/", json=payload, headers=headers)
    assert res1.status_code == 201
    data1 = res1.json()

    # Second request: Replays cached invoice
    res2 = client.post("/invoices/", json=payload, headers=headers)
    assert res2.status_code == 200
    assert res2.headers.get("X-Idempotent-Replay") == "true"
    data2 = res2.json()

    # Assert IDs and totals match exactly
    assert data1["id"] == data2["id"]
    assert data1["total_amount"] == data2["total_amount"]

    # Verify database has exactly 1 invoice
    count = db_session.query(Invoice).count()
    assert count == 1


def test_idempotency_differing_payload_returns_409_conflict(client):
    """Ensure reusing an Idempotency-Key with a modified payload returns HTTP 409 Conflict."""
    payload1 = {
        "customer_name": "Alice Inc",
        "customer_email": "alice@example.com",
        "items": [{"description": "Item 1", "quantity": 1, "unit_price": "50.00"}],
    }
    payload2 = {
        "customer_name": "Alice Inc",
        "customer_email": "alice@example.com",
        "items": [{"description": "Item 2 - Modified", "quantity": 2, "unit_price": "75.00"}],
    }
    headers = {"Idempotency-Key": "conflict_test_key_456"}

    res1 = client.post("/invoices/", json=payload1, headers=headers)
    assert res1.status_code == 201

    res2 = client.post("/invoices/", json=payload2, headers=headers)
    assert res2.status_code == 409
    data2 = res2.json()
    assert data2["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert "was previously used with a different request payload" in data2["error"]["message"]


def test_distinct_idempotency_keys_create_distinct_invoices(client, db_session):
    """Ensure distinct idempotency keys create separate invoices."""
    payload = {
        "customer_name": "Bob LLC",
        "customer_email": "bob@example.com",
        "items": [{"description": "License", "quantity": 1, "unit_price": "150.00"}],
    }
    res1 = client.post("/invoices/", json=payload, headers={"Idempotency-Key": "key_001"})
    res2 = client.post("/invoices/", json=payload, headers={"Idempotency-Key": "key_002"})

    assert res1.status_code == 201
    assert res2.status_code == 201
    assert res1.json()["id"] != res2.json()["id"]
    assert db_session.query(Invoice).count() == 2


# ============================================================================
# Task 3: Pydantic Validation Tests (Strict Types, Negative Values, Extras)
# ============================================================================

def test_validation_missing_customer_name(client):
    """Reject request missing customer_name with HTTP 422."""
    payload = {
        "customer_email": "valid@email.com",
        "items": [{"description": "Service", "quantity": 1, "unit_price": "10.00"}],
    }
    response = client.post("/invoices/", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_validation_invalid_email(client):
    """Reject invalid email format with HTTP 422."""
    payload = {
        "customer_name": "John Doe",
        "customer_email": "not-an-email-address",
        "items": [],
    }
    response = client.post("/invoices/", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_validation_negative_quantity(client):
    """Reject negative quantity in invoice line item with HTTP 422."""
    payload = {
        "customer_name": "Negative Corp",
        "customer_email": "neg@corp.com",
        "items": [{"description": "Item", "quantity": -5, "unit_price": "20.00"}],
    }
    response = client.post("/invoices/", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_validation_zero_quantity(client):
    """Reject zero quantity in invoice line item with HTTP 422."""
    payload = {
        "customer_name": "Zero Qty Corp",
        "customer_email": "zero@corp.com",
        "items": [{"description": "Item", "quantity": 0, "unit_price": "20.00"}],
    }
    response = client.post("/invoices/", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_validation_negative_unit_price(client):
    """Reject negative unit price with HTTP 422."""
    payload = {
        "customer_name": "Negative Price Corp",
        "customer_email": "price@corp.com",
        "items": [{"description": "Item", "quantity": 1, "unit_price": "-10.00"}],
    }
    response = client.post("/invoices/", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_validation_invalid_tax_rate(client):
    """Reject tax rate exceeding 1.00 (100%) or below 0.00 with HTTP 422."""
    payload_high = {
        "customer_name": "High Tax",
        "customer_email": "tax@corp.com",
        "tax_rate": "1.5000",
        "items": [],
    }
    response_high = client.post("/invoices/", json=payload_high)
    assert response_high.status_code == 422

    payload_low = {
        "customer_name": "Negative Tax",
        "customer_email": "tax@corp.com",
        "tax_rate": "-0.0500",
        "items": [],
    }
    response_low = client.post("/invoices/", json=payload_low)
    assert response_low.status_code == 422


def test_validation_rejects_extra_fields(client):
    """Ensure unexpected fields are strictly forbidden by Pydantic model configuration."""
    payload = {
        "customer_name": "Hacker Corp",
        "customer_email": "hacker@corp.com",
        "items": [],
        "illegal_injected_field": "exploit",
    }
    response = client.post("/invoices/", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ============================================================================
# Task 4: Standard API Error Status Codes & Response Envelopes
# ============================================================================

def test_get_invoice_not_found(client):
    """Verify 404 status code and error envelope when querying non-existent invoice."""
    response = client.get("/invoices/inv_nonexistent_999")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert "inv_nonexistent_999" in data["error"]["message"]


def test_invoice_lifecycle_state_transitions(client):
    """Test valid state transitions and 409 Conflict rejection for illegal transitions."""
    # 1. Create invoice (initial status: ISSUED)
    create_res = client.post(
        "/invoices/",
        json={
            "customer_name": "Lifecycle Inc",
            "customer_email": "life@cycle.com",
            "items": [{"description": "Monthly Plan", "quantity": 1, "unit_price": "100.00"}],
        },
    )
    assert create_res.status_code == 201
    inv_id = create_res.json()["id"]
    assert create_res.json()["status"] == "ISSUED"

    # 2. Pay invoice -> PAID
    pay_res = client.post(f"/invoices/{inv_id}/pay")
    assert pay_res.status_code == 200
    assert pay_res.json()["status"] == "PAID"

    # 3. Re-paying invoice is idempotent -> returns 200 and PAID
    repay_res = client.post(f"/invoices/{inv_id}/pay")
    assert repay_res.status_code == 200
    assert repay_res.json()["status"] == "PAID"

    # 4. Attempting to cancel a PAID invoice returns 409 Conflict
    cancel_res = client.post(f"/invoices/{inv_id}/cancel")
    assert cancel_res.status_code == 409
    data = cancel_res.json()
    assert data["error"]["code"] == "INVALID_STATE_TRANSITION"
    assert "Cannot transition invoice from 'PAID' to 'CANCELLED'" in data["error"]["message"]


def test_cannot_pay_cancelled_invoice(client):
    """Verify that attempting to pay a CANCELLED invoice yields HTTP 409 Conflict."""
    create_res = client.post(
        "/invoices/",
        json={
            "customer_name": "Cancel First LLC",
            "customer_email": "cancel@first.com",
            "items": [{"description": "Consulting", "quantity": 1, "unit_price": "200.00"}],
        },
    )
    inv_id = create_res.json()["id"]

    # Cancel invoice
    cancel_res = client.post(f"/invoices/{inv_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

    # Attempt to pay
    pay_res = client.post(f"/invoices/{inv_id}/pay")
    assert pay_res.status_code == 409
    assert pay_res.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


# ============================================================================
# Task 5: Data Consistency & ACID Transaction Safety (Rollbacks)
# ============================================================================

def test_atomic_transaction_rollback_on_item_failure(monkeypatch, client, db_session):
    """Simulate mid-transaction failure during line item insertion.

    Verify that rollback succeeds and zero orphan invoice header records exist in the database.
    """
    original_add = db_session.add

    def mock_add(instance):
        # Allow Invoice to be added, but fail when adding the first InvoiceItem
        if isinstance(instance, InvoiceItem):
            raise RuntimeError("Simulated Database I/O / Constraint Failure on line items")
        original_add(instance)

    monkeypatch.setattr(db_session, "add", mock_add)

    payload = {
        "customer_name": "Rollback Test Ltd",
        "customer_email": "rollback@test.com",
        "items": [
            {"description": "Item 1", "quantity": 1, "unit_price": "50.00"},
            {"description": "Item 2", "quantity": 2, "unit_price": "25.00"},
        ],
    }

    # Request should trigger exception and return 500 error envelope
    response = client.post("/invoices/", json=payload)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"

    # Crucial assertion: The invoice was rolled back! No orphan invoice records exist.
    assert db_session.query(Invoice).count() == 0
    assert db_session.query(InvoiceItem).count() == 0


# ============================================================================
# Adversarial & Boundary Tests
# ============================================================================

def test_adversarial_malformed_json_body(client):
    """Send broken / malformed JSON string payload."""
    response = client.post(
        "/invoices/",
        content="{ customer_name: missing_quotes, malformed",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_adversarial_sql_injection_payload(client, db_session):
    """Verify SQL injection strings are safely treated as literal text values."""
    sql_injection_name = "Acme Corp'; DROP TABLE invoices; --"
    payload = {
        "customer_name": sql_injection_name,
        "customer_email": "safe@acme.com",
        "items": [{"description": "Safety check", "quantity": 1, "unit_price": "10.00"}],
    }
    response = client.post("/invoices/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["customer_name"] == sql_injection_name

    # Check table is still intact and record was saved safely
    inv = db_session.query(Invoice).filter(Invoice.id == data["id"]).first()
    assert inv is not None
    assert inv.customer_name == sql_injection_name


def test_list_invoices_pagination_and_filtering(client):
    """Test pagination offsets, limits, and status filtering on the invoice list endpoint."""
    # Create 3 invoices
    for i in range(3):
        client.post(
            "/invoices/",
            json={
                "customer_name": f"Customer {i}",
                "customer_email": f"cust{i}@example.com",
                "items": [{"description": "Item", "quantity": 1, "unit_price": "10.00"}],
            },
        )

    # Test limit=2
    res = client.get("/invoices/?skip=0&limit=2")
    assert res.status_code == 200
    assert len(res.json()) == 2

    # Test filter by status ISSUED
    res_issued = client.get("/invoices/?status=ISSUED")
    assert res_issued.status_code == 200
    assert len(res_issued.json()) == 3

    # Test filter by status PAID (should be 0)
    res_paid = client.get("/invoices/?status=PAID")
    assert res_paid.status_code == 200
    assert len(res_paid.json()) == 0
