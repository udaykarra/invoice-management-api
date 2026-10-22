"""Candidate Valid Solution A: Explicit iterative accumulator using Decimal."""

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Union
from tasks.invoice_total.contract import InvoiceTotals, LineItem

SCALE = Decimal("0.01")


def calculate_invoice_totals(
    items: List[Union[LineItem, dict]],
    tax_rate: Union[Decimal, str],
) -> InvoiceTotals:
    rate = Decimal(str(tax_rate))
    if not (Decimal("0.00") <= rate <= Decimal("1.00")):
        raise ValueError("Invalid tax rate range")

    subtotal = Decimal("0.00")
    for item in items:
        q = item.quantity if isinstance(item, LineItem) else item["quantity"]
        p = item.unit_price if isinstance(item, LineItem) else item["unit_price"]

        if not isinstance(q, int) or q <= 0:
            raise ValueError("Invalid quantity")
        p_dec = Decimal(str(p))
        if p_dec < Decimal("0.00"):
            raise ValueError("Negative unit price")
        if p_dec.as_tuple().exponent < -2:
            raise ValueError("Unit price exceeds 2 decimal scale")

        line_sum = (Decimal(q) * p_dec).quantize(SCALE, rounding=ROUND_HALF_UP)
        subtotal += line_sum

    subtotal = subtotal.quantize(SCALE, rounding=ROUND_HALF_UP)
    tax = (subtotal * rate).quantize(SCALE, rounding=ROUND_HALF_UP)
    total = (subtotal + tax).quantize(SCALE, rounding=ROUND_HALF_UP)
    return InvoiceTotals(subtotal=subtotal, tax_amount=tax, total_amount=total)
