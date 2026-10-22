"""Flawed Candidate 1: Uses native floats instead of Decimal (fails precision & drift)."""

from decimal import Decimal
from typing import List, Union
from tasks.invoice_total.contract import InvoiceTotals, LineItem


def calculate_invoice_totals(
    items: List[Union[LineItem, dict]],
    tax_rate: Union[Decimal, str],
) -> InvoiceTotals:
    rate = float(tax_rate)
    subtotal = 0.0
    for item in items:
        q = item.quantity if isinstance(item, LineItem) else item["quantity"]
        p = float(item.unit_price if isinstance(item, LineItem) else item["unit_price"])
        subtotal += q * p

    tax = subtotal * rate
    total = subtotal + tax

    # Naive float conversion introduces precision drift on pennies
    return InvoiceTotals(
        subtotal=Decimal(str(subtotal)),
        tax_amount=Decimal(str(tax)),
        total_amount=Decimal(str(total)),
    )
