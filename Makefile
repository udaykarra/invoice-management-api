.PHONY: install run test test-concurrency test-postgres mutation verify lint typecheck test-all help

PYTHON ?= python
PIP ?= pip

help:
	@echo "Available commands:"
	@echo "  make install           Install development and test dependencies"
	@echo "  make run               Run local FastAPI development server"
	@echo "  make test              Run core unit and validation test suite"
	@echo "  make test-concurrency  Run concurrent idempotency stress tests"
	@echo "  make test-postgres     Run PostgreSQL integration tests"
	@echo "  make mutation          Run automated mutation testing report"
	@echo "  make verify            Execute deterministic contract verifier & benchmarks"
	@echo "  make lint              Run ruff code quality checks"
	@echo "  make typecheck         Run mypy static type analysis"
	@echo "  make test-all          Run full verification pipeline"

install:
	$(PIP) install -r requirements-dev.txt

run:
	uvicorn app.main:app --reload --port 8000

test:
	pytest tests/test_invoices.py -v

test-concurrency:
	pytest tests/test_concurrency.py -v

test-postgres:
	pytest tests/test_postgres_integration.py -v

mutation:
	$(PYTHON) scripts/run_mutation_tests.py

verify:
	$(PYTHON) verifier.py

lint:
	ruff check app tests tasks verifier.py scripts

typecheck:
	mypy app

test-all: lint typecheck test test-concurrency mutation verify
	@echo "All verification checks completed successfully!"

