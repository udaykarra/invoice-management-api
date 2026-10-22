"""Deterministic test suite for validating candidate implementations of invoice_total."""

from decimal import Decimal
from tasks.invoice_total.contract import LineItem

VALID_TEST_CASES = [
    {
        "name": "Standard Multiple Items with 10% Tax",
        "items": [
            LineItem(description="Cloud Server", quantity=3, unit_price=Decimal("100.10")),
            LineItem(description="Disk Storage", quantity=7, unit_price=Decimal("0.20")),
            LineItem(description="Bandwidth GB", quantity=100, unit_price=Decimal("0.05")),
        ],
        "tax_rate": "0.1000",
        "expected_subtotal": Decimal("306.70"),
        "expected_tax": Decimal("30.67"),
        "expected_total": Decimal("337.37"),
    },
    {
        "name": "Commercial Half-Up Rounding on Fractional Cents (0.045 -> 0.05 vs 0.04)",
        "items": [
            LineItem(description="Rounding Widget", quantity=1, unit_price=Decimal("10.00")),
        ],
        "tax_rate": "0.0045",
        "expected_subtotal": Decimal("10.00"),
        "expected_tax": Decimal("0.05"),
        "expected_total": Decimal("10.05"),
    },
    {
        "name": "Zero Percent Tax",
        "items": [
            LineItem(description="Tax Exempt Service", quantity=2, unit_price=Decimal("250.00")),
        ],
        "tax_rate": "0.0000",
        "expected_subtotal": Decimal("500.00"),
        "expected_tax": Decimal("0.00"),
        "expected_total": Decimal("500.00"),
    },
    {
        "name": "Empty Line Items Collection",
        "items": [],
        "tax_rate": "0.2000",
        "expected_subtotal": Decimal("0.00"),
        "expected_tax": Decimal("0.00"),
        "expected_total": Decimal("0.00"),
    },
    {
        "name": "Zero Dollar Unit Price",
        "items": [
            LineItem(description="Free Tier Plan", quantity=1, unit_price=Decimal("0.00")),
        ],
        "tax_rate": "0.1000",
        "expected_subtotal": Decimal("0.00"),
        "expected_tax": Decimal("0.00"),
        "expected_total": Decimal("0.00"),
    },
    {
        "name": "Dict-formatted Item Representation Compatibility",
        "items": [
            {"description": "Dict Item", "quantity": 2, "unit_price": Decimal("15.50")},
        ],
        "tax_rate": "0.0500",
        "expected_subtotal": Decimal("31.00"),
        "expected_tax": Decimal("1.55"),
        "expected_total": Decimal("32.55"),
    },
]

MALFORMED_TEST_CASES = [
    {
        "name": "Negative Quantity Rejection",
        "items": [LineItem(description="Bad Qty", quantity=-1, unit_price=Decimal("10.00"))],
        "tax_rate": "0.1000",
        "expected_error": ValueError,
    },
    {
        "name": "Zero Quantity Rejection",
        "items": [LineItem(description="Zero Qty", quantity=0, unit_price=Decimal("10.00"))],
        "tax_rate": "0.1000",
        "expected_error": ValueError,
    },
    {
        "name": "Negative Unit Price Rejection",
        "items": [LineItem(description="Neg Price", quantity=1, unit_price=Decimal("-10.00"))],
        "tax_rate": "0.1000",
        "expected_error": ValueError,
    },
    {
        "name": "Unit Price Scale Exceeds Two Decimal Places (10.999)",
        "items": [LineItem(description="Unscaled", quantity=1, unit_price=Decimal("10.999"))],
        "tax_rate": "0.1000",
        "expected_error": ValueError,
    },
    {
        "name": "Tax Rate Exceeds 100% (1.50)",
        "items": [],
        "tax_rate": "1.5000",
        "expected_error": ValueError,
    },
]
