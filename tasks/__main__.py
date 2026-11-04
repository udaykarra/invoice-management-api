"""CLI entry point for running the AI coding benchmark suite."""
import sys

from tasks.run_all import main

if __name__ == "__main__":
    sys.exit(main())
