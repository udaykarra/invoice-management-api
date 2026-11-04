"""Flawed candidate using Python's default round-to-even (Banker's rounding)."""

from decimal import Decimal
from typing import List, Optional, Union

from tasks.invoice_discount.contract import DiscountType, InvoiceDiscountTotals, LineItem


def calculate_invoice_totals(
    items: List[Union[LineItem, dict]],
    tax_rate: Union[Decimal, str],
    discount_type: Optional[Union[DiscountType, str]] = None,
    discount_value: Optional[Union[Decimal, str]] = None,
) -> InvoiceDiscountTotals:
    rate = Decimal(str(tax_rate))
    subtotal = Decimal("0.00")
    for raw in items:
        qty = raw.quantity if isinstance(raw, LineItem) else raw["quantity"]
        price = Decimal(str(raw.unit_price if isinstance(raw, LineItem) else raw["unit_price"]))
        # Defect: Banker's rounding
        subtotal += Decimal(str(round(qty * float(price), 2)))

    discount_amount = Decimal("0.00")
    if discount_type is not None:
        disc_val_dec = Decimal(str(discount_value))
        if str(discount_type).endswith("PERCENTAGE"):
            # Defect: round-to-even
            discount_amount = Decimal(str(round(float(subtotal) * float(disc_val_dec), 2)))
        else:
            discount_amount = min(subtotal, Decimal(str(round(float(disc_val_dec), 2))))

    discounted_subtotal = max(Decimal("0.00"), subtotal - discount_amount)
    tax_amount = Decimal(str(round(float(discounted_subtotal) * float(rate), 2)))
    total_amount = discounted_subtotal + tax_amount

    return InvoiceDiscountTotals(
        subtotal=subtotal,
        discount_amount=discount_amount,
        discounted_subtotal=discounted_subtotal,
        tax_amount=tax_amount,
        total_amount=total_amount,
    )
