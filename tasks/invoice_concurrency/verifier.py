"""Deterministic verifier for invoice_concurrency candidate solutions."""

import os
import sys
from typing import Tuple

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from tasks.invoice_concurrency.contract import ConcurrentInvoiceHandler
from tasks.invoice_concurrency.test_cases import (
    test_concurrent_conflicting_batch,
    test_concurrent_identical_batch,
)


def verify_implementation(handler: ConcurrentInvoiceHandler) -> Tuple[bool, str]:
    """Test a candidate handler under both identical and conflicting concurrency stress tests."""
    ok_identical, msg_identical = test_concurrent_identical_batch(handler, num_workers=10)
    if not ok_identical:
        return False, f"Identical batch failed: {msg_identical}"

    ok_conflict, msg_conflict = test_concurrent_conflicting_batch(handler, num_workers=10)
    if not ok_conflict:
        return False, f"Conflict batch failed: {msg_conflict}"

    return True, "All concurrent idempotency stress checks passed."


def run_benchmark_verification() -> int:
    """Run verification across reference, valid alternative, and flawed implementations."""
    from tasks.invoice_concurrency.solutions.candidate_valid_lock import handler as valid_lock
    from tasks.invoice_concurrency.solutions.correct import handler as ref_impl
    from tasks.invoice_concurrency.solutions.wrong_no_conflict_check import handler as flawed_conflict
    from tasks.invoice_concurrency.solutions.wrong_race_condition import handler as flawed_race

    candidates = [
        ("Reference Implementation", ref_impl, True),
        ("Candidate A (Valid Mutex/Lock)", valid_lock, True),
        ("Candidate Flawed 1 (Unmitigated Race / 500 Crash)", flawed_race, False),
        ("Candidate Flawed 2 (Missing 409 Conflict Check)", flawed_conflict, False),
    ]

    print("\n------------------------------------------------------------")
    print("  TASK: invoice_concurrency - MULTI-CANDIDATE SOLUTION VERIFIER")
    print("------------------------------------------------------------")

    failures = 0
    for name, handler, expected_pass in candidates:
        try:
            passed, msg = verify_implementation(handler)
            if passed == expected_pass:
                status = "\033[92m[CORRECT BEHAVIOR]\033[0m"
                outcome = "Passed (as expected)" if passed else f"Rejected (as expected: {msg})"
                print(f"  {status} {name:50} -> {outcome}")
            else:
                status = "\033[91m[BENCHMARK ERROR]\033[0m"
                print(f"  {status} {name:50} -> Expected pass={expected_pass}, got pass={passed} ({msg})")
                failures += 1
        except Exception as infra_err:
            status = "\033[91m[INFRA ERROR]\033[0m"
            print(f"  {status} {name:50} -> Verifier Infrastructure Failure: {infra_err}")
            failures += 1

    print("------------------------------------------------------------\n")
    return failures


if __name__ == "__main__":
    sys.exit(run_benchmark_verification())
