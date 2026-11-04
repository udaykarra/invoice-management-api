#!/usr/bin/env python3
"""Top-level evaluation benchmark orchestrator for AI coding evaluation tasks.

Executes all 3 tasks with process isolation and timeout guards:
1. tasks/invoice_total
2. tasks/invoice_discount
3. tasks/invoice_concurrency

Note: Subprocess execution provides runtime fault isolation (preventing sys.exit,
uncaught exceptions, and memory state pollution from crashing the runner).
It is not an unrestricted security sandbox.
"""

import os
import subprocess
import sys
import time
from typing import Tuple

TASKS = [
    ("Task 1: Invoice Total Calculation", os.path.join("tasks", "invoice_total", "verifier.py")),
    ("Task 2: Invoice Discount Feature", os.path.join("tasks", "invoice_discount", "verifier.py")),
    ("Task 3: Concurrent Idempotency", os.path.join("tasks", "invoice_concurrency", "verifier.py")),
]

TIMEOUT_SECONDS = 60


def run_benchmark_task(name: str, script_path: str) -> Tuple[bool, str, float]:
    """Execute a task verifier in an isolated subprocess with timeout."""
    start = time.time()
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    full_path = os.path.join(repo_root, script_path)

    if not os.path.exists(full_path):
        return False, f"Benchmark script missing: {full_path}", 0.0

    env = os.environ.copy()
    env["PYTHONPATH"] = repo_root

    try:
        proc = subprocess.run(
            [sys.executable, full_path],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        duration = time.time() - start
        output = proc.stdout + "\n" + proc.stderr
        passed = (proc.returncode == 0)
        return passed, output.strip(), duration
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        return False, f"TIMEOUT: Verification exceeded {TIMEOUT_SECONDS}s time limit.", duration
    except Exception as e:
        duration = time.time() - start
        return False, f"Subprocess invocation failure: {type(e).__name__}: {str(e)}", duration


def main() -> int:
    print("\n========================================================")
    print("  AI CODING EVALUATION BENCHMARK - MASTER RUNNER")
    print("========================================================\n")

    total_tasks = len(TASKS)
    passed_tasks = 0
    start_all = time.time()

    for name, script_path in TASKS:
        print(f">>> Running {name} ({script_path})...")
        passed, output, duration = run_benchmark_task(name, script_path)
        if passed:
            passed_tasks += 1
            print(f"    \033[92m[PASSED]\033[0m in {duration:.2f}s")
            # Print indentation for inner report
            for line in output.splitlines():
                if line.strip():
                    print(f"      {line}")
        else:
            print(f"    \033[91m[FAILED]\033[0m in {duration:.2f}s")
            for line in output.splitlines():
                if line.strip():
                    print(f"      {line}")
        print()

    total_time = time.time() - start_all
    print("========================================================")
    print(f"  Benchmark Summary: {passed_tasks}/{total_tasks} Tasks Passed ({total_time:.2f}s)")
    print("========================================================\n")

    return 0 if passed_tasks == total_tasks else 1


if __name__ == "__main__":
    sys.exit(main())
