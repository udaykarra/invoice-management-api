# Task: `invoice_discount` (AI Candidate Solution Evaluation Benchmark)

## Overview
This task evaluates AI coding agents and backend engineers on implementing invoice discount business logic adhering to commercial accounting standards, precision rounding, and boundary enforcement.

---

## Problem Statement
Implement `calculate_discounted_invoice_totals(items, tax_rate, discount_type, discount_value) -> InvoiceDiscountTotals`:
1. Calculate line item products and gross `subtotal` using `ROUND_HALF_UP` on fractional cents.
2. If `discount_type` is specified:
   - `PERCENTAGE`: Compute `discount_amount = round_half_up(subtotal * discount_value)`. `discount_value` must be between `0.00` and `1.00`.
   - `FIXED`: Fixed dollar discount with at most 2 decimal places. Capped at `subtotal` so `discounted_subtotal` never drops below `0.00`.
3. Compute `discounted_subtotal = max(0.00, subtotal - discount_amount)`.
4. Sales tax is assessed against `discounted_subtotal`: `tax_amount = round_half_up(discounted_subtotal * tax_rate)`.
5. Grand total: `total_amount = round_half_up(discounted_subtotal + tax_amount)`.

---

## Precise Acceptance Criteria

| Requirement | Contract Rule |
|---|---|
| **Precision** | Strict `decimal.Decimal` arithmetic. Floating-point numbers are prohibited. |
| **Rounding Policy** | Commercial standard **`ROUND_HALF_UP`** (`Decimal("0.01")`). |
| **Fixed Discount Capping** | Fixed discounts exceeding subtotal must be clamped to subtotal (discounted subtotal cannot be negative). |
| **Tax Interaction** | Sales tax must be calculated on the discounted subtotal, never on undiscounted subtotal or post-tax. |
| **Input Validation** | Negative discounts, discount rates $> 1.00$, fixed discount scale $> 2$, and invalid discount types must raise `ValueError`. |

---

## Callable Contract Specification
```python
from decimal import Decimal
from typing import List, Optional, Union
from tasks.invoice_discount.contract import DiscountType, InvoiceDiscountTotals, LineItem

def calculate_discounted_invoice_totals(
    items: List[Union[LineItem, dict]],
    tax_rate: Union[Decimal, str],
    discount_type: Optional[Union[DiscountType, str]] = None,
    discount_value: Optional[Union[Decimal, str]] = None,
) -> InvoiceDiscountTotals:
    ...
```

---

## Running Verification
```bash
python tasks/invoice_discount/verifier.py
```

