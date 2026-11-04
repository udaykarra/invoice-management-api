"""Flawed candidate that fails to cap discounts at subtotal, permitting negative invoice totals."""

from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional, Union

from tasks.invoice_discount.contract import DiscountType, InvoiceDiscountTotals, LineItem

TWO_PLACES = Decimal("0.01")


def round_half_up(val: Decimal) -> Decimal:
    return val.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


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
        subtotal += round_half_up(Decimal(qty) * price)

    subtotal = round_half_up(subtotal)
    discount_amount = Decimal("0.00")

    if discount_type is not None:
        disc_val_dec = Decimal(str(discount_value))
        # Defect: Fixed discount is NOT capped at subtotal, resulting in negative discounted subtotal
        discount_amount = round_half_up(disc_val_dec)

    discounted_subtotal = round_half_up(subtotal - discount_amount)
    tax_amount = round_half_up(discounted_subtotal * rate)
    total_amount = round_half_up(discounted_subtotal + tax_amount)

    return InvoiceDiscountTotals(
        subtotal=subtotal,
        discount_amount=discount_amount,
        discounted_subtotal=discounted_subtotal,
        tax_amount=tax_amount,
        total_amount=total_amount,
    )
