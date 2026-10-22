#!/usr/bin/env python3
"""Standalone Deterministic Contract Verifier for the Invoice Management API.

Acts as an automated contract tester:
- Spawns the FastAPI application with an isolated in-memory SQLite database.
- Feeds deterministic inputs and validates strict behavioral contracts (HTTP codes,
  JSON schema contracts, exact decimal math, idempotency invariants, ACID rollbacks).
- Runs independently without pytest: `python verifier.py`.
- Exits with 0 on complete contract compliance, 1 on any violation.
"""

import sys
import time
from decimal import Decimal
from typing import Callable, List, Tuple
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Invoice, InvoiceItem


class Colors:
    """ANSI color escapes for clean terminal reporting."""
    GREEN = "\033[92m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


class ContractVerifier:
    """Deterministic contract verification test harness."""

    def __init__(self):
        # Create dedicated in-memory database with StaticPool
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionFactory = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine, expire_on_commit=False
        )
        Base.metadata.create_all(bind=self.engine)
        self.session = self.SessionFactory()

        def override_get_db():
            try:
                yield self.session
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)
        self.results: List[Tuple[str, bool, str]] = []

    def close(self):
        """Tear down database session and reset overrides."""
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        app.dependency_overrides.clear()

    def record(self, contract_name: str, passed: bool, detail: str = ""):
        self.results.append((contract_name, passed, detail))
        status = f"{Colors.GREEN}[PASS]{Colors.RESET}" if passed else f"{Colors.RED}[FAIL]{Colors.RESET}"
        print(f"  {status} {contract_name}")
        if not passed and detail:
            print(f"         {Colors.RED}Detail: {detail}{Colors.RESET}")

    def run_contract(self, name: str, test_fn: Callable[[], None]):
        try:
            test_fn()
            self.record(name, True)
        except AssertionError as e:
            self.record(name, False, str(e))
        except Exception as e:
            self.record(name, False, f"Unexpected error: {type(e).__name__}: {str(e)}")

    # -------------------------------------------------------------------------
    # Contract Specifications
    # -------------------------------------------------------------------------

    def verify_health_check(self):
        res = self.client.get("/health")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        assert res.json().get("status") == "healthy", "Health status must be 'healthy'"

    def verify_exact_decimal_math(self):
        payload = {
            "customer_name": "Contract Test Client",
            "customer_email": "contract@test.com",
            "currency": "USD",
            "tax_rate": "0.1000",
            "items": [
                {"description": "Item A", "quantity": 3, "unit_price": "100.10"},
                {"description": "Item B", "quantity": 7, "unit_price": "0.20"},
            ],
        }
        res = self.client.post("/invoices/", json=payload)
        assert res.status_code == 201, f"Expected 201, got {res.status_code}"
        data = res.json()
        assert Decimal(str(data["subtotal"])) == Decimal("301.70"), f"Subtotal mismatch: {data['subtotal']}"
        assert Decimal(str(data["tax_amount"])) == Decimal("30.17"), f"Tax mismatch: {data['tax_amount']}"
        assert Decimal(str(data["total_amount"])) == Decimal("331.87"), f"Total mismatch: {data['total_amount']}"

    def verify_round_half_up_contract(self):
        # 10.00 * 0.1245 = 1.245 -> ROUND_HALF_UP rounds strictly to 1.25
        payload = {
            "customer_name": "Rounder Inc",
            "customer_email": "tax@rounder.com",
            "tax_rate": "0.1245",
            "items": [{"description": "Standard Unit", "quantity": 1, "unit_price": "10.00"}],
        }
        res = self.client.post("/invoices/", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert Decimal(str(data["tax_amount"])) == Decimal("1.25"), f"Expected 1.25, got {data['tax_amount']}"
        assert Decimal(str(data["total_amount"])) == Decimal("11.25"), f"Expected 11.25, got {data['total_amount']}"

    def verify_idempotency_replay(self):
        payload = {
            "customer_name": "Idempotent Org",
            "customer_email": "idem@org.com",
            "items": [{"description": "Seat License", "quantity": 2, "unit_price": "45.00"}],
        }
        headers = {"Idempotency-Key": "verifier_idem_key_001"}

        res1 = self.client.post("/invoices/", json=payload, headers=headers)
        assert res1.status_code == 201
        id1 = res1.json()["id"]

        res2 = self.client.post("/invoices/", json=payload, headers=headers)
        assert res2.status_code == 200, f"Expected replay 200, got {res2.status_code}"
        assert res2.headers.get("X-Idempotent-Replay") == "true", "Missing X-Idempotent-Replay header"
        id2 = res2.json()["id"]
        assert id1 == id2, f"Replay IDs do not match: {id1} vs {id2}"

    def verify_idempotency_conflict(self):
        headers = {"Idempotency-Key": "verifier_idem_key_conflict"}
        payload1 = {
            "customer_name": "Conflict Org",
            "customer_email": "conflict@org.com",
            "items": [{"description": "Item A", "quantity": 1, "unit_price": "10.00"}],
        }
        payload2 = {
            "customer_name": "Conflict Org",
            "customer_email": "conflict@org.com",
            "items": [{"description": "Item A Modified", "quantity": 5, "unit_price": "99.00"}],
        }
        self.client.post("/invoices/", json=payload1, headers=headers)
        res2 = self.client.post("/invoices/", json=payload2, headers=headers)
        assert res2.status_code == 409, f"Expected 409 Conflict, got {res2.status_code}"
        assert res2.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    def verify_validation_error_contract(self):
        # Negative quantity
        payload = {
            "customer_name": "Bad Data Ltd",
            "customer_email": "bad@data.com",
            "items": [{"description": "Negative Item", "quantity": -3, "unit_price": "10.00"}],
        }
        res = self.client.post("/invoices/", json=payload)
        assert res.status_code == 422, f"Expected 422, got {res.status_code}"
        data = res.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert isinstance(data["error"]["details"], list)

    def verify_extra_fields_forbidden(self):
        payload = {
            "customer_name": "Strict Schema Corp",
            "customer_email": "strict@corp.com",
            "items": [],
            "unexpected_injected_field": "disallowed",
        }
        res = self.client.post("/invoices/", json=payload)
        assert res.status_code == 422, f"Expected 422 for extra field, got {res.status_code}"
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"

    def verify_not_found_contract(self):
        res = self.client.get("/invoices/inv_non_existent_key")
        assert res.status_code == 404, f"Expected 404, got {res.status_code}"
        data = res.json()
        assert data["error"]["code"] == "RESOURCE_NOT_FOUND"

    def verify_lifecycle_transition_contract(self):
        # Create -> Cancel -> Pay (must fail with 409)
        create_res = self.client.post(
            "/invoices/",
            json={
                "customer_name": "Lifecycle Contract",
                "customer_email": "life@test.com",
                "items": [{"description": "Plan", "quantity": 1, "unit_price": "100.00"}],
            },
        )
        inv_id = create_res.json()["id"]

        cancel_res = self.client.post(f"/invoices/{inv_id}/cancel")
        assert cancel_res.status_code == 200
        assert cancel_res.json()["status"] == "CANCELLED"

        pay_res = self.client.post(f"/invoices/{inv_id}/pay")
        assert pay_res.status_code == 409, f"Expected 409, got {pay_res.status_code}"
        assert pay_res.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    def verify_empty_line_items_zero_total(self):
        payload = {
            "customer_name": "Empty Items LLC",
            "customer_email": "empty@items.com",
            "tax_rate": "0.1500",
            "items": [],
        }
        res = self.client.post("/invoices/", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert Decimal(str(data["subtotal"])) == Decimal("0.00")
        assert Decimal(str(data["tax_amount"])) == Decimal("0.00")
        assert Decimal(str(data["total_amount"])) == Decimal("0.00")

    def verify_atomic_transaction_rollback(self):
        original_add = self.session.add

        def fail_on_item(instance):
            if isinstance(instance, InvoiceItem):
                raise RuntimeError("Contract Verifier: Forced Database Failure")
            original_add(instance)

        self.session.add = fail_on_item
        try:
            payload = {
                "customer_name": "Atomic Rollback Corp",
                "customer_email": "atomic@rollback.com",
                "items": [{"description": "Item", "quantity": 1, "unit_price": "50.00"}],
            }
            res = self.client.post("/invoices/", json=payload)
            assert res.status_code == 500, f"Expected 500 on simulated DB error, got {res.status_code}"
            # Check that database has no orphan invoices matching this customer
            orphan = self.session.query(Invoice).filter(Invoice.customer_name == "Atomic Rollback Corp").first()
            assert orphan is None, "Transaction rollback failed: orphan invoice was committed!"
        finally:
            self.session.add = original_add

    def verify_whitespace_idempotency_key(self):
        payload = {
            "customer_name": "Whitespace Inc",
            "customer_email": "white@inc.com",
            "items": [{"description": "Item", "quantity": 1, "unit_price": "10.00"}],
        }
        res = self.client.post("/invoices/", json=payload, headers={"Idempotency-Key": "   "})
        assert res.status_code == 400, f"Expected 400 Bad Request, got {res.status_code}"
        assert res.json()["error"]["code"] == "BAD_REQUEST"

    def verify_unit_price_scale_constraint(self):
        payload = {
            "customer_name": "Scale Corp",
            "customer_email": "scale@corp.com",
            "items": [{"description": "Item", "quantity": 1, "unit_price": "10.999"}],
        }
        res = self.client.post("/invoices/", json=payload)
        assert res.status_code == 422, f"Expected 422 for scale > 2, got {res.status_code}"
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def main() -> int:
    print(f"\n{Colors.CYAN}{Colors.BOLD}========================================================")
    print("  INVOICE MANAGEMENT API - DETERMINISTIC CONTRACT VERIFIER")
    print(f"========================================================{Colors.RESET}\n")

    verifier = ContractVerifier()
    start_time = time.time()

    contracts = [
        ("Contract 01: System Health Endpoint (GET /health)", verifier.verify_health_check),
        ("Contract 02: Exact Decimal Financial Math (No Float Drift)", verifier.verify_exact_decimal_math),
        ("Contract 03: Commercial Half-Up Rounding (ROUND_HALF_UP)", verifier.verify_round_half_up_contract),
        ("Contract 04: Idempotency Replay Invariant (Idempotency-Key Header)", verifier.verify_idempotency_replay),
        ("Contract 05: Idempotency Conflict Invariant (409 on Payload Mismatch)", verifier.verify_idempotency_conflict),
        ("Contract 06: Pydantic Schema Validation Invariant (422 Envelope)", verifier.verify_validation_error_contract),
        ("Contract 07: Strict Schema Rejection on Extra Fields", verifier.verify_extra_fields_forbidden),
        ("Contract 08: Missing Entity Schema Contract (404 Not Found)", verifier.verify_not_found_contract),
        ("Contract 09: Lifecycle State Transition Guard (409 on Invalid Flow)", verifier.verify_lifecycle_transition_contract),
        ("Contract 10: Empty Collection & Zero Arithmetic Compliance", verifier.verify_empty_line_items_zero_total),
        ("Contract 11: ACID Transaction Atomicity & Mid-Flight Rollback", verifier.verify_atomic_transaction_rollback),
        ("Contract 12: Idempotency Key Whitespace Rejection (HTTP 400)", verifier.verify_whitespace_idempotency_key),
        ("Contract 13: Unit Price Decimal Scale Constraint (Max 2 Scale)", verifier.verify_unit_price_scale_constraint),
    ]

    for name, test_fn in contracts:
        verifier.run_contract(name, test_fn)

    duration = time.time() - start_time
    total = len(verifier.results)
    passed = sum(1 for _, ok, _ in verifier.results if ok)
    failed = total - passed

    print(f"\n{Colors.CYAN}--------------------------------------------------------{Colors.RESET}")
    print(f"  API Contracts: {total} | Passed: {Colors.GREEN}{passed}{Colors.RESET} | Failed: {Colors.RED}{failed}{Colors.RESET} ({duration:.2f}s)")
    print(f"{Colors.CYAN}--------------------------------------------------------{Colors.RESET}\n")

    verifier.close()

    # Priority 2: Execute the Candidate Solution Evaluation Benchmark
    from tasks.invoice_total.verifier import run_benchmark_verification
    benchmark_failures = run_benchmark_verification()

    total_failures = failed + benchmark_failures
    if total_failures == 0:
        print(f"{Colors.GREEN}{Colors.BOLD}>>> VERIFICATION SUCCESS: All API contracts & candidate benchmarks passed! <<<{Colors.RESET}\n")
        return 0
    else:
        print(f"{Colors.RED}{Colors.BOLD}>>> VERIFICATION FAILURE: {total_failures} violations detected. <<<{Colors.RESET}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
