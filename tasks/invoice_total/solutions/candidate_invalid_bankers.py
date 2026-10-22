"""Flawed Candidate 2: Uses Python Banker's round() instead of commercial ROUND_HALF_UP."""

from decimal import Decimal
from typing import List, Union
from tasks.invoice_total.contract import InvoiceTotals, LineItem


def calculate_invoice_totals(
    items: List[Union[LineItem, dict]],
    tax_rate: Union[Decimal, str],
) -> InvoiceTotals:
    rate = float(tax_rate)
    if rate < 0 or rate > 1:
        raise ValueError("Invalid tax rate")

    subtotal = 0.0
    for item in items:
        q = item.quantity if isinstance(item, LineItem) else item["quantity"]
        p = float(item.unit_price if isinstance(item, LineItem) else item["unit_price"])
        if not isinstance(q, int) or q <= 0:
            raise ValueError("Invalid quantity")
        if p < 0:
            raise ValueError("Negative price")
        if Decimal(str(p)).as_tuple().exponent < -2:
            raise ValueError("Price exceeds scale")
        subtotal += round(q * p, 2)

    subtotal = round(subtotal, 2)
    # Banker's rounding rounds 1.245 to 1.24 instead of 1.25
    tax = round(subtotal * rate, 2)
    total = round(subtotal + tax, 2)

    return InvoiceTotals(
        subtotal=Decimal(f"{subtotal:.2f}"),
        tax_amount=Decimal(f"{tax:.2f}"),
        total_amount=Decimal(f"{total:.2f}"),
    )
