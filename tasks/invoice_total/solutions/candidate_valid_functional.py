"""Candidate Valid Solution B: Functional map-reduce architecture using Decimal."""

from decimal import Decimal, ROUND_HALF_UP
from functools import reduce
from typing import List, Union
from tasks.invoice_total.contract import InvoiceTotals, LineItem

SCALE = Decimal("0.01")


def _process_item(item: Union[LineItem, dict]) -> Decimal:
    q = item.quantity if isinstance(item, LineItem) else item["quantity"]
    p = item.unit_price if isinstance(item, LineItem) else item["unit_price"]

    if not isinstance(q, int) or q <= 0:
        raise ValueError("Quantity must be positive integer")
    dec_price = Decimal(str(p))
    if dec_price < Decimal("0.00"):
        raise ValueError("Price must be non-negative")
    if dec_price.as_tuple().exponent < -2:
        raise ValueError("Price scale exceeds 2 decimal places")

    return (Decimal(q) * dec_price).quantize(SCALE, rounding=ROUND_HALF_UP)


def calculate_invoice_totals(
    items: List[Union[LineItem, dict]],
    tax_rate: Union[Decimal, str],
) -> InvoiceTotals:
    rate = Decimal(str(tax_rate))
    if rate < Decimal("0.00") or rate > Decimal("1.00"):
        raise ValueError("Tax rate out of bounds [0.0, 1.0]")

    line_totals = list(map(_process_item, items))
    subtotal = reduce(lambda acc, x: acc + x, line_totals, Decimal("0.00")).quantize(SCALE, rounding=ROUND_HALF_UP)
    tax = (subtotal * rate).quantize(SCALE, rounding=ROUND_HALF_UP)
    total = (subtotal + tax).quantize(SCALE, rounding=ROUND_HALF_UP)

    return InvoiceTotals(subtotal=subtotal, tax_amount=tax, total_amount=total)
