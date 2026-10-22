"""Contract and data structures for the invoice_total task."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, List, Union


@dataclass(frozen=True)
class LineItem:
    """Represents a single billable line item."""
    description: str
    quantity: int
    unit_price: Decimal


@dataclass(frozen=True)
class InvoiceTotals:
    """Calculated financial summary of an invoice."""
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal


# Type signature of any conforming candidate implementation
InvoiceTotalFunction = Callable[[List[Union[LineItem, dict]], Union[Decimal, str]], InvoiceTotals]
