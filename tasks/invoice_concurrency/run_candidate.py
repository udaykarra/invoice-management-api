#!/usr/bin/env python3
"""Isolated subprocess runner for invoice_concurrency candidate solutions.

Loads a candidate module in a standalone process, executes concurrent stress tests,
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

from tasks.invoice_concurrency.test_cases import (
    test_concurrent_conflicting_batch,
    test_concurrent_identical_batch,
)


def load_candidate_handler(file_path: str):
    """Dynamically load handler or create handler from file path."""
    spec = importlib.util.spec_from_file_location("concurrency_candidate", file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module spec from {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if hasattr(module, "handler"):
        return getattr(module, "handler")
    elif hasattr(module, "ReferenceConcurrentHandler"):
        cls = getattr(module, "ReferenceConcurrentHandler")
        return cls()
    elif hasattr(module, "process_request"):
        class Wrapper:
            process_request = staticmethod(getattr(module, "process_request"))
        return Wrapper()

    raise AttributeError(f"Module {file_path} missing 'handler' or 'process_request'")


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"passed": False, "message": "Missing candidate file path argument"}))
        sys.exit(1)

    candidate_file = sys.argv[1]
    if not os.path.exists(candidate_file):
        print(json.dumps({"passed": False, "message": f"Candidate file not found: {candidate_file}"}))
        sys.exit(1)

    try:
        handler = load_candidate_handler(candidate_file)
        ok_id, msg_id = test_concurrent_identical_batch(handler, num_workers=10)
        if not ok_id:
            print(json.dumps({"passed": False, "message": f"Identical batch failed: {msg_id}"}))
            sys.exit(1)

        ok_cf, msg_cf = test_concurrent_conflicting_batch(handler, num_workers=10)
        if not ok_cf:
            print(json.dumps({"passed": False, "message": f"Conflict batch failed: {msg_cf}"}))
            sys.exit(1)

        print(json.dumps({"passed": True, "message": "All concurrent stress tests passed."}))
        sys.exit(0)
    except Exception as e:
        print(json.dumps({"passed": False, "message": f"Execution error: {type(e).__name__}: {str(e)}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()

