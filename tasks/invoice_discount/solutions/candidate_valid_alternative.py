"""Alternative valid candidate using functional reductions."""

from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional, Union

from tasks.invoice_discount.contract import DiscountType, InvoiceDiscountTotals, LineItem

SCALE = Decimal("0.01")


def r(v: Decimal) -> Decimal:
    return v.quantize(SCALE, rounding=ROUND_HALF_UP)


def calculate_invoice_totals(
    items: List[Union[LineItem, dict]],
    tax_rate: Union[Decimal, str],
    discount_type: Optional[Union[DiscountType, str]] = None,
    discount_value: Optional[Union[Decimal, str]] = None,
) -> InvoiceDiscountTotals:
    rate = Decimal(str(tax_rate))
    if rate < Decimal("0.00") or rate > Decimal("1.00"):
        raise ValueError("Invalid tax rate")
    if rate.as_tuple().exponent < -4:
        raise ValueError("Tax rate scale exceeds 4")

    def item_total(raw):
        q = raw.quantity if isinstance(raw, LineItem) else raw["quantity"]
        p = Decimal(str(raw.unit_price if isinstance(raw, LineItem) else raw["unit_price"]))
        if not isinstance(q, int) or q <= 0:
            raise ValueError("Positive integer quantity required")
        if p < Decimal("0.00") or p.as_tuple().exponent < -2:
            raise ValueError("Invalid unit price")
        return r(Decimal(q) * p)

    subtotal = r(sum((item_total(x) for x in items), Decimal("0.00")))
    discount_amt = Decimal("0.00")

    if discount_type is not None:
        t = discount_type.value if isinstance(discount_type, DiscountType) else str(discount_type).upper()
        if t not in ("PERCENTAGE", "FIXED"):
            raise ValueError(f"Unknown discount {discount_type}")
        if discount_value is None:
            raise ValueError("Missing value")
        dv = Decimal(str(discount_value))
        if dv < Decimal("0.00"):
            raise ValueError("Negative discount")
        if t == "PERCENTAGE":
            if dv > Decimal("1.00"):
                raise ValueError("Percentage exceeds 100%")
            discount_amt = r(subtotal * dv)
        elif t == "FIXED":
            if dv.as_tuple().exponent < -2:
                raise ValueError("Fixed scale exceeds 2")
            discount_amt = min(subtotal, r(dv))

    disc_subtotal = max(Decimal("0.00"), r(subtotal - discount_amt))
    tax_amt = r(disc_subtotal * rate)
    tot = r(disc_subtotal + tax_amt)

    return InvoiceDiscountTotals(
        subtotal=subtotal,
        discount_amount=discount_amt,
        discounted_subtotal=disc_subtotal,
        tax_amount=tax_amt,
        total_amount=tot,
    )
