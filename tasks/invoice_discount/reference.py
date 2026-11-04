"""Official Reference Implementation for the invoice_discount task."""

from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional, Union

from tasks.invoice_discount.contract import (
    DiscountType,
    InvoiceDiscountTotals,
    LineItem,
)

TWO_PLACES = Decimal("0.01")


def round_half_up(val: Decimal) -> Decimal:
    """Perform commercial standard half-up rounding to two decimal places."""
    return val.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def calculate_discounted_invoice_totals(
    items: List[Union[LineItem, dict]],
    tax_rate: Union[Decimal, str],
    discount_type: Optional[Union[DiscountType, str]] = None,
    discount_value: Optional[Union[Decimal, str]] = None,
) -> InvoiceDiscountTotals:
    """Calculate subtotal, discount, discounted subtotal, tax, and total with commercial rounding."""
    rate = Decimal(str(tax_rate))
    if rate < Decimal("0.00") or rate > Decimal("1.00"):
        raise ValueError(f"Tax rate must be between 0.00 and 1.00, got: {rate}")
    if rate.as_tuple().exponent < -4:
        raise ValueError(f"Tax rate scale cannot exceed 4 decimal places, got: {rate}")

    subtotal = Decimal("0.00")
    for raw in items:
        qty = raw.quantity if isinstance(raw, LineItem) else raw["quantity"]
        price = raw.unit_price if isinstance(raw, LineItem) else raw["unit_price"]

        if not isinstance(qty, int) or qty <= 0:
            raise ValueError(f"Quantity must be a strictly positive integer, got: {qty}")

        price_dec = Decimal(str(price))
        if price_dec < Decimal("0.00"):
            raise ValueError(f"Unit price must be non-negative, got: {price_dec}")
        if price_dec.as_tuple().exponent < -2:
            raise ValueError(f"Unit price must have at most 2 decimal places, got: {price_dec}")

        line_total = round_half_up(Decimal(qty) * price_dec)
        subtotal += line_total

    subtotal = round_half_up(subtotal)
    discount_amount = Decimal("0.00")

    if discount_type is not None:
        disc_type_str = discount_type.value if isinstance(discount_type, DiscountType) else str(discount_type).upper()
        if disc_type_str not in ("PERCENTAGE", "FIXED"):
            raise ValueError(f"Unsupported discount_type: {discount_type}")

        if discount_value is None:
            raise ValueError("discount_value must be provided when discount_type is set")

        disc_val_dec = Decimal(str(discount_value))
        if disc_val_dec < Decimal("0.00"):
            raise ValueError(f"Discount value cannot be negative, got: {disc_val_dec}")

        if disc_type_str == "PERCENTAGE":
            if disc_val_dec > Decimal("1.00"):
                raise ValueError(f"Percentage discount rate cannot exceed 1.00 (100%), got: {disc_val_dec}")
            discount_amount = round_half_up(subtotal * disc_val_dec)
        elif disc_type_str == "FIXED":
            if disc_val_dec.as_tuple().exponent < -2:
                raise ValueError("Fixed discount value cannot exceed 2 decimal places")
            # Fixed discount is capped at subtotal to prevent negative invoice totals
            discount_amount = min(subtotal, round_half_up(disc_val_dec))

    discounted_subtotal = max(Decimal("0.00"), round_half_up(subtotal - discount_amount))
    tax_amount = round_half_up(discounted_subtotal * rate)
    total_amount = round_half_up(discounted_subtotal + tax_amount)

    return InvoiceDiscountTotals(
        subtotal=subtotal,
        discount_amount=discount_amount,
        discounted_subtotal=discounted_subtotal,
        tax_amount=tax_amount,
        total_amount=total_amount,
    )
