# Task: `invoice_total` (AI Candidate Solution Evaluation Benchmark)

## Overview
This task is a benchmark problem designed to evaluate backend code generation systems and candidate engineers. It requires computing financial invoice totals adhering to strict commercial accounting policies and schema boundaries.

---

## Problem Statement
Implement the function `calculate_invoice_totals(items, tax_rate) -> InvoiceTotals` that computes:
1. `subtotal`: The sum of all line item totals (`quantity * unit_price`), rounded to 2 decimal places using `ROUND_HALF_UP`.
2. `tax_amount`: The subtotal multiplied by `tax_rate`, rounded to 2 decimal places using `ROUND_HALF_UP`.
3. `total_amount`: The subtotal plus `tax_amount`, rounded to 2 decimal places using `ROUND_HALF_UP`.

---

## Precise Acceptance Criteria

| Requirement | Contract Rule |
|---|---|
| **Arithmetic Precision** | Must use exact decimal arithmetic (`decimal.Decimal`). Native binary floating-point (`float`) is strictly prohibited. |
| **Rounding Policy** | Must use commercial standard **`ROUND_HALF_UP`** (where half-cent values like `0.005` round up to `0.01`). Python's default round-to-even (Banker's rounding) is rejected. |
| **Monetary Scale** | Subtotal, tax, and total must have an explicit scale of exactly 2 decimal places (`0.01`). |
| **Input Validation** | Line item `quantity` must be a strictly positive integer (`> 0`). `unit_price` must be non-negative with at most 2 decimal places. `tax_rate` must be within `[0.00, 1.00]`. Invalid values must raise `ValueError`. |
| **Empty Items** | An empty `items` collection must evaluate to `subtotal=0.00`, `tax_amount=0.00`, `total_amount=0.00` without raising an exception. |

---

## Callable Contract Specification
```python
from decimal import Decimal
from typing import List, Union
from tasks.invoice_total.contract import InvoiceTotals, LineItem

def calculate_invoice_totals(
    items: List[Union[LineItem, dict]],
    tax_rate: Union[Decimal, str],
) -> InvoiceTotals:
    ...
```

---

## Candidate Implementations Verified

The test harness (`tasks/invoice_total/verifier.py`) tests multiple candidate solutions to ensure multiple valid algorithms pass while flawed ones fail:

- **Reference Implementation (`reference.py`):** Authoritative solution. Passes all contracts.
- **Candidate A (`solutions/candidate_valid_iterative.py`):** Iterative procedural accumulator. Passes all contracts.
- **Candidate B (`solutions/candidate_valid_functional.py`):** Functional `map`-`reduce` architecture. Passes all contracts.
- **Flawed Candidate 1 (`solutions/candidate_invalid_float.py`):** Uses IEEE 754 floats. Fails on precision drift and fractional penny inaccuracies.
- **Flawed Candidate 2 (`solutions/candidate_invalid_bankers.py`):** Uses Python's native `round()`. Fails commercial half-up rounding (e.g. `1.245 -> 1.24`).
- **Flawed Candidate 3 (`solutions/candidate_invalid_unscaled.py`):** Fails to enforce 2-decimal scale limit on `unit_price`. Fails input validation contracts.
- **Flawed Candidate 4 (`solutions/candidate_invalid_negative.py`):** Accepts negative quantities. Fails boundary validation contracts.
