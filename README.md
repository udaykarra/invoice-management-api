# Invoice Management API (Production Reference Architecture)

[![Build & Verify](https://github.com/your-username/invoice-management-api/actions/workflows/python-app.yml/badge.svg)](https://github.com/your-username/invoice-management-api/actions)
![Python 3.10 | 3.11 | 3.12](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688)
![Pydantic v2](https://img.shields.io/badge/Pydantic-v2.6+-e92063)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0+-d71f00)
![Tests](https://img.shields.io/badge/Tests-22%20Passed-brightgreen)
![Contracts](https://img.shields.io/badge/Contract%20Verifier-11%2F11%20Passed-success)

A battle-tested, high-reliability Invoice Management REST API built with **Python**, **FastAPI**, and **SQLAlchemy (SQLite)**. Designed from first principles to demonstrate Staff-level backend craftsmanship: exact financial calculations (`decimal.Decimal`), distributed idempotency key handling, ACID transaction boundaries with rollbacks, strict Pydantic v2 schema boundaries, and deterministic contract verification.

---

## Table of Contents

- [System Architecture](#system-architecture)
- [Directory Structure](#directory-structure)
- [Quickstart & Installation](#quickstart--installation)
- [API Reference & Curl Examples](#api-reference--curl-examples)
- [The 5 Intentional Defect Fixes](#the-5-intentional-defect-fixes)
- [Test Suite & Verification](#test-suite--verification)
- [Deep-Dive: Engineering Decisions](#deep-dive-engineering-decisions)
  - [1. Floating Point vs. Arbitrary Precision Decimal](#1-floating-point-vs-arbitrary-precision-decimal)
  - [2. Distributed Idempotency Key Architecture](#2-distributed-idempotency-key-architecture)
  - [3. Transactional Safety & ACID Guarantees in SQLite](#3-transactional-safety--acid-guarantees-in-sqlite)
- [Debugging Case Study: The "Disappearing Penny" Defect](#debugging-case-study-the-disappearing-penny-defect)

---

## System Architecture

```mermaid
flowchart TD
    Client[API Client / Frontend] -->|HTTP POST /invoices/ + Idempotency-Key| Router[FastAPI Router]
    Router -->|Validate Schema| Pydantic[Pydantic v2 Validator]
    Pydantic -->|Extra field or negative qty?| Reject422[HTTP 422 Validation Error]
    Pydantic -->|Payload Valid| CRUD[CRUD Service Layer]
    
    subgraph Idempotency Check
        CRUD -->|Query Key| IdemTable[(Idempotency Records)]
        IdemTable -->|Key exists & Hash matches| ReturnCached[Replay Cached 200 OK]
        IdemTable -->|Key exists & Hash differs| Conflict409[HTTP 409 Conflict]
    end

    subgraph Atomic ACID Transaction
        CRUD -->|Begin DB Transaction| DB[(SQLite Database)]
        CRUD -->|Exact Math ROUND_HALF_UP| Calc[Decimal Engine]
        Calc -->|Insert Header| InvRow[Invoice Record]
        Calc -->|Insert Line Items| ItemRows[Invoice Items Records]
        Calc -->|Insert Key Hash| IdemInsert[Idempotency Record]
        DB -->|Any step fails?| Rollback[Rollback Everything - No Orphan Records]
        DB -->|All steps succeed| Commit[Commit Transaction]
    end

    Commit --> ReturnCreated[HTTP 201 Created]
```

---

## Directory Structure

```text
.
├── .github/
│   └── workflows/
│       └── python-app.yml       # GitHub Actions CI matrix (Py 3.10, 3.11, 3.12)
├── app/
│   ├── __init__.py             # Package initializer
│   ├── config.py               # Pydantic Settings & environment config
│   ├── crud.py                 # Business logic, math, idempotency, transactions
│   ├── database.py             # Engine, session factory & SQLite foreign keys
│   ├── errors.py               # Unified exception hierarchy & error envelope handlers
│   ├── main.py                 # FastAPI application & route endpoints
│   ├── models.py               # SQLAlchemy ORM models (Invoice, Item, Idempotency)
│   └── schemas.py              # Pydantic v2 schemas (strict validation, forbid extra)
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Pytest fixtures & isolated in-memory DB
│   └── test_invoices.py        # 22 tests (math, idempotency, negative, ACID rollback)
├── .gitignore                  # Git exclusions
├── requirements.txt            # Production dependencies
├── verifier.py                 # Standalone deterministic contract tester
└── README.md                   # Technical documentation & case study
```

---

## Quickstart & Installation

### 1. Prerequisites
- Python 3.10, 3.11, or 3.12
- Git

### 2. Setup Virtual Environment
```bash
# Clone the repository
git clone https://github.com/your-username/invoice-management-api.git
cd invoice-management-api

# Create and activate virtual environment
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Run the Development Server
```bash
uvicorn app.main:app --reload --port 8000
```
- Interactive Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- Interactive ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- Health check: [http://localhost:8000/health](http://localhost:8000/health)

### 4. Run the Pytest Test Suite
```bash
pytest -v
```

### 5. Run the Standalone Contract Verifier
```bash
python verifier.py
```

---

## API Reference & Curl Examples

All responses follow standard HTTP codes. Errors consistently follow the envelope format:
```json
{
  "error": {
    "code": "ERROR_CODE_STRING",
    "message": "Human readable explanation",
    "details": null
  }
}
```

### 1. Create Invoice (with Idempotency Key)
```bash
curl -X POST "http://localhost:8000/invoices/" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: req_live_8392019" \
  -d '{
    "customer_name": "Acme Technologies",
    "customer_email": "billing@acme.com",
    "currency": "USD",
    "tax_rate": "0.0825",
    "notes": "Net 30 payment terms",
    "items": [
      {
        "description": "Dedicated Cloud Hosting (Nov)",
        "quantity": 1,
        "unit_price": "299.00"
      },
      {
        "description": "SSL Certificate Provisioning",
        "quantity": 2,
        "unit_price": "49.50"
      }
    ]
  }'
```

**Response (HTTP 201 Created):**
```json
{
  "id": "inv_a4e89f10c3b2",
  "customer_name": "Acme Technologies",
  "customer_email": "billing@acme.com",
  "status": "ISSUED",
  "currency": "USD",
  "tax_rate": "0.0825",
  "subtotal": "398.00",
  "tax_amount": "32.84",
  "total_amount": "430.84",
  "notes": "Net 30 payment terms",
  "created_at": "2026-10-22T06:30:00",
  "updated_at": "2026-10-22T06:30:00",
  "items": [
    {
      "id": 1,
      "description": "Dedicated Cloud Hosting (Nov)",
      "quantity": 1,
      "unit_price": "299.00",
      "line_total": "299.00"
    },
    {
      "id": 2,
      "description": "SSL Certificate Provisioning",
      "quantity": 2,
      "unit_price": "49.50",
      "line_total": "99.00"
    }
  ]
}
```

*Note: If this exact curl command is executed again with the same `Idempotency-Key`, it returns the identical invoice with `HTTP 200 OK` and `X-Idempotent-Replay: true` without creating a duplicate record in the database.*

### 2. List Invoices (with Pagination & Filtering)
```bash
curl -X GET "http://localhost:8000/invoices/?skip=0&limit=10&status=ISSUED"
```

### 3. Retrieve Invoice by ID
```bash
curl -X GET "http://localhost:8000/invoices/inv_a4e89f10c3b2"
```

### 4. Transition Invoice to PAID
```bash
curl -X POST "http://localhost:8000/invoices/inv_a4e89f10c3b2/pay"
```

### 5. Transition Invoice to CANCELLED
```bash
curl -X POST "http://localhost:8000/invoices/inv_a4e89f10c3b2/cancel"
```
*(Attempting to pay a cancelled invoice or cancel a paid invoice returns `409 Conflict`.)*

---

## The 5 Intentional Defect Fixes

| Task / Defect | Vulnerability in Naive Code | Production Hardening Implemented |
|---|---|---|
| **Task 1: Math** | Binary `float` IEEE 754 precision drift (e.g. `0.1 + 0.2 != 0.3`) and banker's rounding discrepancies. | Exact `decimal.Decimal` throughout the domain with deterministic `ROUND_HALF_UP`. Graceful handling of zero amounts and empty items lists. |
| **Task 2: Idempotency** | Network retries create duplicate invoices and double-bill customers. | Stripe-style `Idempotency-Key` header with SHA-256 payload hashing. Safe replay (`200 OK`) on match, rejection (`409 Conflict`) on modified payload. |
| **Task 3: Validation** | Missing customer names, negative quantities, arbitrary field injection. | Pydantic v2 schemas configured with `extra="forbid"`, `gt=0` quantity constraints, regex email validation, and strict boundary caps. |
| **Task 4: Error Handling** | Inconsistent error responses, uncaught 500 tracebacks leaking internals. | Standard HTTP status mapping (`400`, `404`, `409`, `422`, `500`) wrapped in a uniform `{ "error": { "code", "message", "details" } }` schema envelope. |
| **Task 5: ACID Safety** | Partial writes leave orphan invoice headers when line items fail to insert. | SQLAlchemy session transaction boundary with explicit `db.flush()`, `db.commit()`, and `db.rollback()` on any failure. Foreign keys enforced in SQLite. |

---

## Test Suite & Verification

The repository includes a two-tier verification strategy:

### 1. Pytest Test Suite (`tests/test_invoices.py`)
- **22 automated tests** covering unit calculations, database transactions, boundary cases, and negative paths.
- Uses an in-memory SQLite database (`sqlite:///:memory:`) with `StaticPool` to ensure tests execute in complete isolation without mutating local files.
- Includes simulated database failure tests to guarantee transaction rollbacks prevent orphan records.
- Adversarial tests: Malformed JSON syntax, SQL injection payloads in string fields, unicode characters.

Run:
```bash
pytest -v
```

### 2. Standalone Contract Verifier (`verifier.py`)
- Zero third-party testing runner required.
- Programmatically boots the application in-process and validates 11 critical contracts:
  1. System Health Endpoint (`GET /health`)
  2. Exact Decimal Financial Math
  3. Commercial Half-Up Rounding (`ROUND_HALF_UP`)
  4. Idempotency Replay Invariant (`X-Idempotent-Replay`)
  5. Idempotency Conflict Invariant (409 on altered payload)
  6. Pydantic Schema Validation Envelope (`422`)
  7. Strict Schema Rejection on Extra Fields
  8. Missing Entity Envelope (`404`)
  9. Lifecycle State Transition Guard (`409`)
  10. Empty Collection & Zero Arithmetic Compliance
  11. ACID Transaction Atomicity & Mid-Flight Rollback

Run:
```bash
python verifier.py
```

---

## Deep-Dive: Engineering Decisions

### 1. Floating Point vs. Arbitrary Precision Decimal

#### The Problem: IEEE 754 Binary Representation
In IEEE 754 standard floating-point representation, numbers are stored as base-2 fractions. Fractions like `0.10` (10 cents) cannot be represented precisely in binary, resulting in an infinite repeating fraction:
$$\frac{1}{10} = 0.0001100110011..._2$$

In Python:
```python
>>> 0.1 + 0.2
0.30000000000000004
>>> 0.1 + 0.2 == 0.3
False
```
In a ledger or billing system aggregating thousands of line items, floating-point rounding errors compound, producing ledger imbalances, auditing failures, and regulatory non-compliance under GAAP and IFRS rules.

#### The Solution: Python `decimal.Decimal` + `ROUND_HALF_UP`
We represent every monetary field (`unit_price`, `line_total`, `subtotal`, `tax_rate`, `tax_amount`, `total_amount`) as Python `Decimal` objects:
```python
TWO_PLACES = Decimal("0.01")

def round_currency(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
```
- **Why `ROUND_HALF_UP`?** Python's default `round()` function uses *Banker's Rounding* (round-to-even), where `2.5 -> 2` and `3.5 -> 4`. While statistically neutral for large scientific data, consumer billing and tax authorities (e.g., IRS, HMRC) mandate standard commercial half-up rounding (where fractional values $\ge 0.005$ always round up to the nearest cent).

---

### 2. Distributed Idempotency Key Architecture

#### The Problem: The Double-Billing Danger of Network Retries
Distributed systems are prone to network timeouts. When a client submits an invoice creation request and experiences a network drop before receiving the response:
- The server may have already committed the invoice.
- The client, unaware of the server's state, automatically retries the POST request.
- Without idempotency protection, a duplicate invoice is created and the client is double-charged.

```text
Client                       Server
  |                            |
  |--- POST /invoices/ ------->| (Processes invoice, inserts into DB)
  |      [Network Drop]        | (Sends 201 Created, but client never gets it)
  |           X                |
  |                            |
  |--- POST /invoices/ ------->| (Duplicate invoice created! Double billing defect!)
```

#### The Solution: Key Hashing and Atomic State Tracking
We implement the IETF draft standard for HTTP Idempotency Keys:

1. **Header Extraction:** Clients supply an optional `Idempotency-Key: <unique-uuid>`.
2. **Payload Canonicalization & Hashing:**
   The request JSON is serialized with sorted keys and normalized delimiters, then hashed using SHA-256:
   ```python
   canonical_json = json.dumps(payload_dict, sort_keys=True, separators=(",", ":"), default=str)
   payload_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
   ```
3. **Lookup & Conflict Detection:**
   - **Case A (Cache Hit & Matching Hash):** The client is retrying an identical request. We retrieve the original response from the `idempotency_records` table and replay it with `HTTP 200 OK` and `X-Idempotent-Replay: true`.
   - **Case B (Key Reused with Mismatched Hash):** A client reused an old idempotency key with a new/different request payload. This is an unambiguous client bug. The API rejects the request immediately with `HTTP 409 Conflict` and code `IDEMPOTENCY_CONFLICT`.
   - **Case C (First Encounter):** The transaction creates the invoice, line items, and the idempotency record atomically in a single database transaction.

---

### 3. Transactional Safety & ACID Guarantees in SQLite

#### The Problem: Relational Inconsistency via Mid-Flight Failures
Creating an invoice is a composite operation requiring writes across multiple relational tables:
1. Insert into `invoices` (header)
2. Insert $N$ rows into `invoice_items` (line items)
3. Insert into `idempotency_records` (idempotency key audit)

If step 1 succeeds but step 2 fails (e.g. disk full, constraint violation, foreign key failure), a naive service leaves an orphan invoice header with no line items and zero subtotal.

#### The Solution: Strict Unit of Work & SQLite Pragmas
1. **SQLite Foreign Keys:** By default, SQLite has foreign key enforcement disabled for backwards compatibility. We attach an engine listener on connection creation:
   ```python
   @event.listens_for(Engine, "connect")
   def set_sqlite_pragma(dbapi_connection, connection_record):
       cursor = dbapi_connection.cursor()
       cursor.execute("PRAGMA foreign_keys=ON")
       cursor.close()
   ```
2. **Atomic Session Management:** All writes occur inside a managed session block. If any step raises an exception, `db.rollback()` executes, reverting the database to its pristine pre-request state:
   ```python
   try:
       db.add(db_invoice)
       db.flush()
       for item in items:
           db.add(db_item)
       db.flush()
       db.commit()
   except Exception:
       db.rollback()
       raise
   ```

---

## Debugging Case Study: The "Disappearing Penny" Defect

### 1. Incident Summary
- **Severity:** High (Financial Inaccuracy)
- **Component:** Billing / Invoice Calculation Engine
- **Reported Symptom:** Customer invoices with multiple line items exhibited a 1-cent discrepancy between the printed `total_amount` and the sum of displayed line items plus tax.

### 2. Investigation & Reproduction
A customer was billed for 3 items at \$100.10, 7 items at \$0.20, and 100 items at \$0.05 with a 10% tax rate.

**Original (Flawed) Implementation:**
```python
# BUGGY IMPLEMENTATION
subtotal = 0.0
for item in payload["items"]:
    line_total = round(item["quantity"] * item["unit_price"], 2)
    subtotal += line_total

tax_amount = round(subtotal * payload["tax_rate"], 2)
total_amount = round(subtotal + tax_amount, 2)
```

Running this with standard Python floats:
```python
subtotal = 3 * 100.10 + 7 * 0.20 + 100 * 0.05
# subtotal = 300.29999999999995 + 1.4000000000000001 + 5.0
# subtotal evaluates to 306.69999999999993
# round(subtotal, 2) produces 306.7
```
When complex combinations of sales tax rates (e.g. 8.25% or 7.5%) were applied, binary rounding produced rounding in the *wrong direction* on half-cent values:
```python
# Flawed Banker's Rounding:
round(1.245, 2) # -> 1.24 (Banker's rounds 4 to even!)
```
Under tax regulations, \$1.245 must round to **\$1.25**. The company was under-remitting sales tax by one penny on thousands of invoices.

### 3. Root Cause Analysis
1. **Binary Float Drift:** Python `float` is an IEEE 754 64-bit double precision value. It cannot store fractional base-10 values like `0.10` without precision loss.
2. **Banker's Rounding:** Python's built-in `round()` function employs round-to-even behavior, which is incompatible with commercial tax accounting standards.

### 4. Remediation & Verification
1. Replaced all float types in Pydantic schemas and database models with `decimal.Decimal` and `Numeric(12, 2, asdecimal=True)`.
2. Created a centralized rounding helper utilizing `decimal.ROUND_HALF_UP`:
   ```python
   def round_currency(value: Decimal) -> Decimal:
       return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
   ```
3. Added a regression test (`test_rounding_half_up_behavior` in `tests/test_invoices.py`):
   ```python
   def test_rounding_half_up_behavior(client):
       payload = {
           "customer_name": "Rounding Corp",
           "customer_email": "finance@rounding.com",
           "tax_rate": "0.1245",
           "items": [{"description": "Widget", "quantity": 1, "unit_price": "10.00"}],
       }
       res = client.post("/invoices/", json=payload)
       assert res.status_code == 201
       assert Decimal(str(res.json()["tax_amount"])) == Decimal("1.25")
   ```

---

## License

This project is licensed under the MIT License.
