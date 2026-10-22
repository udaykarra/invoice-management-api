"""Official Reference Implementation for the invoice_total task."""

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Union
from tasks.invoice_total.contract import InvoiceTotals, LineItem

TWO_PLACES = Decimal("0.01")


def round_half_up(val: Decimal) -> Decimal:
    """Perform commercial standard half-up rounding to two decimal places."""
    return val.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def calculate_invoice_totals(
    items: List[Union[LineItem, dict]],
    tax_rate: Union[Decimal, str],
) -> InvoiceTotals:
    """Calculate subtotal, tax_amount, and total_amount according to commercial standard."""
    rate = Decimal(str(tax_rate))
    if rate < Decimal("0.00") or rate > Decimal("1.00"):
        raise ValueError(f"Tax rate must be between 0.00 and 1.00, got: {rate}")

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
    tax_amount = round_half_up(subtotal * rate)
    total_amount = round_half_up(subtotal + tax_amount)

    return InvoiceTotals(
        subtotal=subtotal,
        tax_amount=tax_amount,
        total_amount=total_amount,
    )
