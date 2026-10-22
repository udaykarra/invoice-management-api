"""Flawed Candidate 3: Fails to validate that unit_price has at most 2 decimal places."""

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Union
from tasks.invoice_total.contract import InvoiceTotals, LineItem

SCALE = Decimal("0.01")


def calculate_invoice_totals(
    items: List[Union[LineItem, dict]],
    tax_rate: Union[Decimal, str],
) -> InvoiceTotals:
    rate = Decimal(str(tax_rate))
    if rate < 0 or rate > 1:
        raise ValueError("Invalid tax rate")

    subtotal = Decimal("0.00")
    for item in items:
        q = item.quantity if isinstance(item, LineItem) else item["quantity"]
        p = item.unit_price if isinstance(item, LineItem) else item["unit_price"]

        if not isinstance(q, int) or q <= 0:
            raise ValueError("Invalid quantity")
        p_dec = Decimal(str(p))
        if p_dec < 0:
            raise ValueError("Negative price")

        # Missing scale check: silently accepts e.g. 10.999
        line_sum = (Decimal(q) * p_dec).quantize(SCALE, rounding=ROUND_HALF_UP)
        subtotal += line_sum

    tax = (subtotal * rate).quantize(SCALE, rounding=ROUND_HALF_UP)
    total = (subtotal + tax).quantize(SCALE, rounding=ROUND_HALF_UP)
    return InvoiceTotals(subtotal=subtotal, tax_amount=tax, total_amount=total)
