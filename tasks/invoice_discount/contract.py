"""Contract and data structures for the invoice_discount task."""

import enum
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, List, Optional, Union


class DiscountType(str, enum.Enum):
    """Supported invoice discount mechanisms."""
    PERCENTAGE = "PERCENTAGE"
    FIXED = "FIXED"


@dataclass(frozen=True)
class LineItem:
    """Represents a single billable line item."""
    description: str
    quantity: int
    unit_price: Decimal


@dataclass(frozen=True)
class InvoiceDiscountTotals:
    """Calculated financial summary of an invoice with discounts applied."""
    subtotal: Decimal
    discount_amount: Decimal
    discounted_subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal


# Type signature of any conforming candidate implementation
InvoiceDiscountFunction = Callable[
    [
        List[Union[LineItem, dict]],
        Union[Decimal, str],
        Optional[Union[DiscountType, str]],
        Optional[Union[Decimal, str]],
    ],
    InvoiceDiscountTotals,
]

