#!/usr/bin/env python3
"""Automated Mutation Testing Harness for the Invoice Management API.

Tests whether the test suite detects and kills 10 intentional financial, idempotency,
and database transaction defects:

1. Decimal replaced with float in financial arithmetic (accumulating precision drift)
2. ROUND_HALF_UP replaced with ROUND_HALF_EVEN (Banker's rounding)
3. Negative quantity validation removed from Pydantic schema
4. Idempotency conflict detection removed (mismatched payloads accepted)
5. Transaction rollback removed on failure (committing partial state)
6. Invoice grand total calculation broken (omitting sales tax)
7. Discount calculation made incorrect (uncapped fixed discount in benchmark)
8. Duplicate invoice creation introduced (ignoring idempotency key entirely)
9. Monetary precision validation removed (accepting 3 decimal places)
10. Database consistency broken during mid-flight transaction failures (premature commit)

Generates an empirical, reproducible report.
"""

import os
import subprocess
import sys
import time
from typing import Tuple


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def apply_mutation_to_file(filepath: str, target: str, replacement: str) -> Tuple[str, bool]:
    """Read a file, apply replacement, write to disk, return original content."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if target not in content:
        return content, False

    mutated = content.replace(target, replacement, 1)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(mutated)
    return content, True


def restore_file(filepath: str, original_content: str):
    """Restore file content."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(original_content)


def run_targeted_test(test_target: str) -> bool:
    """Run pytest on test_target. Returns True if tests pass, False if tests fail (killed)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = REPO_ROOT
    res = subprocess.run(
        [sys.executable, "-m", "pytest", test_target, "-q", "--tb=no"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    return res.returncode == 0


MUTATIONS = [
    {
        "id": "MUT-01",
        "name": "Decimal replaced with float in financial arithmetic (precision drift)",
        "file": os.path.join(REPO_ROOT, "app", "crud.py"),
        "target": """    subtotal = Decimal("0.00")
    for item in items:
        line_total = calculate_line_total(item.quantity, item.unit_price)
        subtotal += line_total

    subtotal = round_currency(subtotal)
    tax_amount = round_currency(subtotal * tax_rate)
    total_amount = round_currency(subtotal + tax_amount)
    return subtotal, tax_amount, total_amount""",
        "replacement": """    subtotal_f = sum(float(item.quantity) * float(item.unit_price) for item in items)
    subtotal = Decimal(str(subtotal_f))
    tax_amount = Decimal(str(subtotal_f * float(tax_rate)))
    total_amount = Decimal(str(subtotal_f + float(tax_amount)))
    return subtotal, tax_amount, total_amount""",
        "test": "tests/test_invoices.py::test_invoice_creation_exact_decimal_calculation",
    },
    {
        "id": "MUT-02",
        "name": "ROUND_HALF_UP replaced with ROUND_HALF_EVEN (Banker's rounding)",
        "file": os.path.join(REPO_ROOT, "app", "crud.py"),
        "target": 'return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)',
        "replacement": 'from decimal import ROUND_HALF_EVEN\n    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_EVEN)',
        "test": "tests/test_invoices.py::test_rounding_half_up_behavior",
    },
    {
        "id": "MUT-03",
        "name": "Negative quantity validation removed from schema",
        "file": os.path.join(REPO_ROOT, "app", "schemas.py"),
        "target": "gt=0,",
        "replacement": "# gt=0 removed",
        "test": "tests/test_invoices.py::test_validation_negative_quantity",
    },
    {
        "id": "MUT-04",
        "name": "Idempotency conflict detection removed (payload mismatch ignored)",
        "file": os.path.join(REPO_ROOT, "app", "crud.py"),
        "target": "raise IdempotencyConflictException(cleaned_key)",
        "replacement": "return InvoiceResponse.model_validate_json(existing_rec.response_body), False",
        "test": "tests/test_invoices.py::test_idempotency_differing_payload_returns_409_conflict",
    },
    {
        "id": "MUT-05",
        "name": "Transaction rollback removed during transaction failure (commit partial)",
        "file": os.path.join(REPO_ROOT, "app", "crud.py"),
        "target": """        except Exception:
            db.rollback()
            raise""",
        "replacement": """        except Exception:
            db.commit()
            raise""",
        "test": "tests/test_invoices.py::test_atomic_transaction_rollback_on_item_failure",
    },
    {
        "id": "MUT-06",
        "name": "Invoice total calculation broken (omitting sales tax)",
        "file": os.path.join(REPO_ROOT, "app", "crud.py"),
        "target": "total_amount = round_currency(subtotal + tax_amount)",
        "replacement": "total_amount = round_currency(subtotal)",
        "test": "tests/test_invoices.py::test_invoice_creation_exact_decimal_calculation",
    },
    {
        "id": "MUT-07",
        "name": "Discount calculation made incorrect (uncapped fixed discount)",
        "file": os.path.join(REPO_ROOT, "tasks", "invoice_discount", "reference.py"),
        "target": "discount_amount = min(subtotal, round_half_up(disc_val_dec))",
        "replacement": "discount_amount = round_half_up(disc_val_dec)",
        "test": "tasks/invoice_discount/verifier.py",
    },
    {
        "id": "MUT-08",
        "name": "Duplicate invoice creation introduced (cleaned_key forced to None)",
        "file": os.path.join(REPO_ROOT, "app", "crud.py"),
        "target": "cleaned_key = idempotency_key.strip() if idempotency_key else None",
        "replacement": "cleaned_key = None",
        "test": "tests/test_invoices.py::test_idempotency_identical_payload_returns_cached_invoice",
    },
    {
        "id": "MUT-09",
        "name": "Monetary precision validation removed (scale constraint omitted)",
        "file": os.path.join(REPO_ROOT, "app", "schemas.py"),
        "target": 'raise ValueError("unit_price must have at most 2 decimal places")',
        "replacement": "pass",
        "test": "tests/test_invoices.py::test_validation_unit_price_exceeding_two_decimal_places",
    },
    {
        "id": "MUT-10",
        "name": "Database consistency broken during transaction failures (premature commit)",
        "file": os.path.join(REPO_ROOT, "app", "crud.py"),
        "target": """            db.add(db_invoice)
            db.flush()

            for item_in in invoice_in.items:""",
        "replacement": """            db.add(db_invoice)
            db.commit()

            for item_in in invoice_in.items:""",
        "test": "tests/test_invoices.py::test_atomic_transaction_rollback_on_item_failure",
    },
]


def run_mutation_verification() -> int:
    print(f"\n{Colors.CYAN}{Colors.BOLD}========================================================")
    print("  AUTOMATED MUTATION TESTING REPORT (10 INTENTIONAL DEFECTS)")
    print(f"========================================================{Colors.RESET}\n")

    killed = 0
    survived = 0
    start_time = time.time()

    for mut in MUTATIONS:
        mut_id = mut["id"]
        name = mut["name"]
        filepath = mut["file"]
        target = mut["target"]
        replacement = mut["replacement"]
        test_target = mut["test"]

        # 1. Apply mutation
        original, applied = apply_mutation_to_file(filepath, target, replacement)
        if not applied:
            print(f"  {Colors.YELLOW}[ERROR]{Colors.RESET} Could not apply {mut_id}: target pattern not found in {os.path.basename(filepath)}")
            survived += 1
            continue

        try:
            # 2. Run targeted test
            if test_target.endswith(".py") and "::" not in test_target:
                proc = subprocess.run([sys.executable, test_target], cwd=REPO_ROOT, capture_output=True, text=True)
                test_passed = (proc.returncode == 0)
            else:
                test_passed = run_targeted_test(test_target)

            # 3. Determine if mutation was killed (test failing means mutation was detected and killed!)
            if not test_passed:
                killed += 1
                status = f"{Colors.GREEN}[KILLED]{Colors.RESET}"
                detail = f"Caught by: {test_target.split('::')[-1]}"
            else:
                survived += 1
                status = f"{Colors.RED}[SURVIVED]{Colors.RESET}"
                detail = f"FAILED TO CATCH by: {test_target}"

            print(f"  {status} {mut_id}: {name}")
            print(f"           {detail}")

        finally:
            # 4. Restore original content unconditionally
            restore_file(filepath, original)

    duration = time.time() - start_time
    total = killed + survived
    score = (killed / total * 100.0) if total > 0 else 0.0

    print(f"\n{Colors.CYAN}--------------------------------------------------------{Colors.RESET}")
    print(f"  Total Mutations: {total} | Killed: {Colors.GREEN}{killed}{Colors.RESET} | Survived: {Colors.RED}{survived}{Colors.RESET} ({duration:.2f}s)")
    print(f"  Mutation Score: {Colors.BOLD}{score:.1f}%{Colors.RESET}")
    print(f"{Colors.CYAN}--------------------------------------------------------{Colors.RESET}\n")

    if survived == 0:
        print(f"{Colors.GREEN}{Colors.BOLD}>>> MUTATION TESTING SUCCESS: All 10 intentional defects killed! (100.0%) <<<{Colors.RESET}\n")
        return 0
    else:
        print(f"{Colors.RED}{Colors.BOLD}>>> MUTATION TESTING FAILURE: {survived} mutations survived! <<<{Colors.RESET}\n")
        return 1


if __name__ == "__main__":
    sys.exit(run_mutation_verification())
