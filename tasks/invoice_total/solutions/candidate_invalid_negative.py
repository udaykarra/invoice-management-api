"""Flawed Candidate 4: Fails to reject negative or zero quantities."""

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Union
from tasks.invoice_total.contract import InvoiceTotals, LineItem

SCALE = Decimal("0.01")


def calculate_invoice_totals(
    items: List[Union[LineItem, dict]],
    tax_rate: Union[Decimal, str],
) -> InvoiceTotals:
    rate = Decimal(str(tax_rate))
    subtotal = Decimal("0.00")
    for item in items:
        q = item.quantity if isinstance(item, LineItem) else item["quantity"]
        p = item.unit_price if isinstance(item, LineItem) else item["unit_price"]

        # Missing quantity check: negative quantity allowed
        line_sum = (Decimal(q) * Decimal(str(p))).quantize(SCALE, rounding=ROUND_HALF_UP)
        subtotal += line_sum

    tax = (subtotal * rate).quantize(SCALE, rounding=ROUND_HALF_UP)
    total = (subtotal + tax).quantize(SCALE, rounding=ROUND_HALF_UP)
    return InvoiceTotals(subtotal=subtotal, tax_amount=tax, total_amount=total)
