import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from decimal import Decimal
from typing import Callable, Tuple
from tasks.invoice_total.contract import InvoiceTotals, InvoiceTotalFunction
from tasks.invoice_total.test_cases import VALID_TEST_CASES, MALFORMED_TEST_CASES


def verify_implementation(candidate_fn: InvoiceTotalFunction) -> Tuple[bool, str]:
    """Test a candidate function against all validity and malformed input contracts.

    Returns:
        (passed: bool, message: str)
    """
    # 1. Test Valid Functional Cases
    for tc in VALID_TEST_CASES:
        try:
            result = candidate_fn(tc["items"], tc["tax_rate"])
        except Exception as e:
            return False, f"Failed on valid test '{tc['name']}': Raised unexpected exception: {e}"

        if not isinstance(result, InvoiceTotals):
            return False, f"Return type must be InvoiceTotals, got {type(result).__name__}"

        if result.subtotal != tc["expected_subtotal"]:
            return False, f"Test '{tc['name']}': subtotal mismatch. Expected {tc['expected_subtotal']}, got {result.subtotal}"

        if result.tax_amount != tc["expected_tax"]:
            return False, f"Test '{tc['name']}': tax_amount mismatch. Expected {tc['expected_tax']}, got {result.tax_amount}"

        if result.total_amount != tc["expected_total"]:
            return False, f"Test '{tc['name']}': total_amount mismatch. Expected {tc['expected_total']}, got {result.total_amount}"

    # 2. Test Malformed / Negative Cases
    for tc in MALFORMED_TEST_CASES:
        try:
            candidate_fn(tc["items"], tc["tax_rate"])
            return False, f"Test '{tc['name']}': Expected {tc['expected_error'].__name__} was NOT raised."
        except Exception as e:
            if not isinstance(e, tc["expected_error"]):
                return False, f"Test '{tc['name']}': Expected {tc['expected_error'].__name__}, but caught {type(e).__name__}: {e}"

    return True, "All test cases passed."


def run_benchmark_verification() -> int:
    """Run verification across reference, valid variants, and deliberately flawed implementations."""
    from tasks.invoice_total.reference import calculate_invoice_totals as ref_impl
    from tasks.invoice_total.solutions.candidate_valid_iterative import calculate_invoice_totals as valid_a
    from tasks.invoice_total.solutions.candidate_valid_functional import calculate_invoice_totals as valid_b
    from tasks.invoice_total.solutions.candidate_invalid_float import calculate_invoice_totals as invalid_float
    from tasks.invoice_total.solutions.candidate_invalid_bankers import calculate_invoice_totals as invalid_bankers
    from tasks.invoice_total.solutions.candidate_invalid_unscaled import calculate_invoice_totals as invalid_unscaled
    from tasks.invoice_total.solutions.candidate_invalid_negative import calculate_invoice_totals as invalid_negative

    candidates = [
        ("Reference Implementation", ref_impl, True),
        ("Candidate A (Valid Iterative)", valid_a, True),
        ("Candidate B (Valid Functional)", valid_b, True),
        ("Candidate Flawed 1 (Float Precision Drift)", invalid_float, False),
        ("Candidate Flawed 2 (Banker's Rounding)", invalid_bankers, False),
        ("Candidate Flawed 3 (Unscaled Decimal Acceptance)", invalid_unscaled, False),
        ("Candidate Flawed 4 (Negative Quantity Accepted)", invalid_negative, False),
    ]

    print("\n------------------------------------------------------------")
    print("  TASK: invoice_total - MULTI-CANDIDATE SOLUTION VERIFIER")
    print("------------------------------------------------------------")

    failures = 0
    for name, fn, expected_pass in candidates:
        passed, msg = verify_implementation(fn)
        if passed == expected_pass:
            status = "\033[92m[CORRECT BEHAVIOR]\033[0m"
            outcome = "Passed (as expected)" if passed else f"Rejected (as expected: {msg})"
            print(f"  {status} {name:48} -> {outcome}")
        else:
            status = "\033[91m[BENCHMARK ERROR]\033[0m"
            print(f"  {status} {name:48} -> Expected pass={expected_pass}, got pass={passed} ({msg})")
            failures += 1

    print("------------------------------------------------------------\n")
    return failures


if __name__ == "__main__":
    sys.exit(run_benchmark_verification())
