"""Flawed candidate using IEEE-754 floats."""
from decimal import Decimal
from typing import List, Optional, Union

from tasks.invoice_discount.contract import DiscountType, InvoiceDiscountTotals, LineItem


def calculate_invoice_totals(
    items: List[Union[LineItem, dict]],
    tax_rate: Union[Decimal, str],
    discount_type: Optional[Union[DiscountType, str]] = None,
    discount_value: Optional[Union[Decimal, str]] = None,
) -> InvoiceDiscountTotals:
    rate = float(tax_rate)
    subtotal = 0.0
    for raw in items:
        q = raw.quantity if isinstance(raw, LineItem) else raw["quantity"]
        p = float(raw.unit_price if isinstance(raw, LineItem) else raw["unit_price"])
        subtotal += q * p

    subtotal = round(subtotal, 2)
    discount_amount = 0.0
    if discount_type is not None:
        t = discount_type.value if isinstance(discount_type, DiscountType) else str(discount_type).upper()
        dv = float(discount_value)
        if t == "PERCENTAGE":
            discount_amount = round(subtotal * dv, 2)
        elif t == "FIXED":
            discount_amount = min(subtotal, round(dv, 2))

    disc_subtotal = max(0.0, subtotal - discount_amount)
    tax_amount = round(disc_subtotal * rate, 2)
    total_amount = round(disc_subtotal + tax_amount, 2)

    return InvoiceDiscountTotals(
        subtotal=Decimal(str(subtotal)),
        discount_amount=Decimal(str(discount_amount)),
        discounted_subtotal=Decimal(str(disc_subtotal)),
        tax_amount=Decimal(str(tax_amount)),
        total_amount=Decimal(str(total_amount)),
    )
