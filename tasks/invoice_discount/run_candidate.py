#!/usr/bin/env python3
"""Isolated subprocess runner for invoice_discount candidate solutions.

Loads a candidate module in a standalone process, executes behavioral tests,
and outputs structured JSON diagnostics to stdout.
"""

import importlib.util
import json
import os
import sys

# Ensure repository root is on sys.path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from tasks.invoice_discount.contract import InvoiceDiscountTotals
from tasks.invoice_discount.test_cases import (
    HIDDEN_EVALUATION_TEST_CASES,
    MALFORMED_TEST_CASES,
    PUBLIC_TEST_CASES,
)


def load_candidate_function(file_path: str):
    """Dynamically load calculate_invoice_totals from target file path."""
    spec = importlib.util.spec_from_file_location("candidate_module", file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module spec from {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if hasattr(module, "calculate_invoice_totals"):
        return getattr(module, "calculate_invoice_totals")
    elif hasattr(module, "calculate_discounted_invoice_totals"):
        return getattr(module, "calculate_discounted_invoice_totals")
    raise AttributeError(f"Module {file_path} missing 'calculate_invoice_totals' or 'calculate_discounted_invoice_totals'")


def verify(candidate_fn):
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
            return False, f"Failed on valid test '{tc['name']}': {e}"

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


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"passed": False, "message": "Missing candidate file path argument"}))
        sys.exit(1)

    candidate_file = sys.argv[1]
    if not os.path.exists(candidate_file):
        print(json.dumps({"passed": False, "message": f"Candidate file not found: {candidate_file}"}))
        sys.exit(1)

    try:
        fn = load_candidate_function(candidate_file)
        passed, msg = verify(fn)
        print(json.dumps({"passed": passed, "message": msg}))
        sys.exit(0 if passed else 1)
    except Exception as e:
        print(json.dumps({"passed": False, "message": f"Execution error: {type(e).__name__}: {str(e)}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
