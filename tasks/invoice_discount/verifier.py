"""Deterministic verifier for invoice_discount candidate implementations."""

import os
import sys
from typing import Callable, Tuple

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from tasks.invoice_discount.contract import InvoiceDiscountTotals
from tasks.invoice_discount.test_cases import (
    HIDDEN_EVALUATION_TEST_CASES,
    MALFORMED_TEST_CASES,
    PUBLIC_TEST_CASES,
)


def verify_implementation(candidate_fn: Callable) -> Tuple[bool, str]:
    """Test a candidate function against public, hidden, and malformed cases.

    Returns:
        (passed: bool, message: str)
    """
    all_valid_cases = PUBLIC_TEST_CASES + HIDDEN_EVALUATION_TEST_CASES

    for tc in all_valid_cases:
        try:
            result = candidate_fn(
                tc["items"],
                tc["tax_rate"],
                tc["discount_type"],
                tc["discount_value"],
            )
        except Exception as e:
            return False, f"Candidate error on test '{tc['name']}': Raised exception: {type(e).__name__}: {e}"

        if not isinstance(result, InvoiceDiscountTotals):
            return False, f"Return type must be InvoiceDiscountTotals, got {type(result).__name__}"

        if result.subtotal != tc["expected_subtotal"]:
            return False, f"Test '{tc['name']}': subtotal mismatch. Expected {tc['expected_subtotal']}, got {result.subtotal}"

        if result.discount_amount != tc["expected_discount"]:
            return False, f"Test '{tc['name']}': discount_amount mismatch. Expected {tc['expected_discount']}, got {result.discount_amount}"

        if result.discounted_subtotal != tc["expected_discounted_subtotal"]:
            return False, f"Test '{tc['name']}': discounted_subtotal mismatch. Expected {tc['expected_discounted_subtotal']}, got {result.discounted_subtotal}"

        if result.tax_amount != tc["expected_tax"]:
            return False, f"Test '{tc['name']}': tax_amount mismatch. Expected {tc['expected_tax']}, got {result.tax_amount}"

        if result.total_amount != tc["expected_total"]:
            return False, f"Test '{tc['name']}': total_amount mismatch. Expected {tc['expected_total']}, got {result.total_amount}"

    for tc in MALFORMED_TEST_CASES:
        try:
            candidate_fn(
                tc["items"],
                tc["tax_rate"],
                tc["discount_type"],
                tc["discount_value"],
            )
            return False, f"Test '{tc['name']}': Expected {tc['expected_error'].__name__} was NOT raised."
        except Exception as e:
            if not isinstance(e, tc["expected_error"]):
                return False, f"Test '{tc['name']}': Expected {tc['expected_error'].__name__}, but caught {type(e).__name__}: {e}"

    return True, "All valid and adversarial test cases passed."


def run_benchmark_verification() -> int:
    """Run verification across reference, valid variants, and flawed implementations."""
    from tasks.invoice_discount.reference import calculate_discounted_invoice_totals as ref_impl
    from tasks.invoice_discount.solutions.candidate_valid_alternative import calculate_invoice_totals as valid_alt
    from tasks.invoice_discount.solutions.wrong_discount_order import calculate_invoice_totals as wrong_order
    from tasks.invoice_discount.solutions.wrong_float import calculate_invoice_totals as wrong_float
    from tasks.invoice_discount.solutions.wrong_negative_total import calculate_invoice_totals as wrong_neg
    from tasks.invoice_discount.solutions.wrong_rounding import calculate_invoice_totals as wrong_round

    candidates = [
        ("Reference Implementation", ref_impl, True),
        ("Candidate A (Valid Alternative)", valid_alt, True),
        ("Candidate Flawed 1 (Float Drift)", wrong_float, False),
        ("Candidate Flawed 2 (Uncapped Negative Subtotal)", wrong_neg, False),
        ("Candidate Flawed 3 (Tax Before Discount Order)", wrong_order, False),
        ("Candidate Flawed 4 (Banker's Rounding)", wrong_round, False),
    ]

    print("\n------------------------------------------------------------")
    print("  TASK: invoice_discount - MULTI-CANDIDATE SOLUTION VERIFIER")
    print("------------------------------------------------------------")

    failures = 0
    for name, fn, expected_pass in candidates:
        try:
            passed, msg = verify_implementation(fn)
            if passed == expected_pass:
                status = "\033[92m[CORRECT BEHAVIOR]\033[0m"
                outcome = "Passed (as expected)" if passed else f"Rejected (as expected: {msg})"
                print(f"  {status} {name:48} -> {outcome}")
            else:
                status = "\033[91m[BENCHMARK ERROR]\033[0m"
                print(f"  {status} {name:48} -> Expected pass={expected_pass}, got pass={passed} ({msg})")
                failures += 1
        except Exception as infra_err:
            status = "\033[91m[INFRA ERROR]\033[0m"
            print(f"  {status} {name:48} -> Verifier Infrastructure Failure: {infra_err}")
            failures += 1

    print("------------------------------------------------------------\n")
    return failures


if __name__ == "__main__":
    sys.exit(run_benchmark_verification())
