#!/usr/bin/env python3
"""Multi-candidate verifier for invoice_discount with subprocess isolation.

Candidate solutions are evaluated in isolated Python subprocesses with:
- Execution timeouts (5.0s per candidate).
- Controlled input/output via structured JSON over stdout.
- Fault isolation against unhandled exceptions, process exits, or state mutations.
- Clear exit codes and diagnostic error reporting.

Note: Subprocess execution provides runtime fault isolation, not an unrestricted
OS-level security sandbox.
"""

import json
import os
import subprocess
import sys
from typing import Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
EVAL_RUNNER = os.path.join(os.path.dirname(__file__), "run_candidate.py")
TIMEOUT_SECONDS = 5.0


def verify_candidate_isolated(candidate_rel_path: str) -> Tuple[bool, str]:
    """Execute candidate verification inside an isolated subprocess with timeout."""
    candidate_abs_path = os.path.join(REPO_ROOT, candidate_rel_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = REPO_ROOT

    try:
        proc = subprocess.run(
            [sys.executable, EVAL_RUNNER, candidate_abs_path],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        stdout_clean = proc.stdout.strip()
        if stdout_clean:
            try:
                data = json.loads(stdout_clean)
                return bool(data.get("passed", False)), str(data.get("message", "No message"))
            except json.JSONDecodeError:
                pass

        err_msg = proc.stderr.strip() or f"Subprocess exited with code {proc.returncode}"
        return False, err_msg
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT: Candidate exceeded {TIMEOUT_SECONDS}s execution limit"
    except Exception as e:
        return False, f"Subprocess invocation failure: {type(e).__name__}: {str(e)}"


def run_benchmark_verification() -> int:
    """Run verification across reference, valid variants, and flawed implementations."""
    candidates = [
        ("Reference Implementation", "tasks/invoice_discount/reference.py", True),
        ("Candidate A (Valid Alternative)", "tasks/invoice_discount/solutions/candidate_valid_alternative.py", True),
        ("Candidate Flawed 1 (Float Drift)", "tasks/invoice_discount/solutions/wrong_float.py", False),
        ("Candidate Flawed 2 (Uncapped Negative Subtotal)", "tasks/invoice_discount/solutions/wrong_negative_total.py", False),
        ("Candidate Flawed 3 (Tax Before Discount Order)", "tasks/invoice_discount/solutions/wrong_discount_order.py", False),
        ("Candidate Flawed 4 (Banker's Rounding)", "tasks/invoice_discount/solutions/wrong_rounding.py", False),
    ]

    print("\n------------------------------------------------------------")
    print("  TASK: invoice_discount - MULTI-CANDIDATE SOLUTION VERIFIER")
    print("------------------------------------------------------------")

    failures = 0
    for name, rel_path, expected_pass in candidates:
        passed, msg = verify_candidate_isolated(rel_path)
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
