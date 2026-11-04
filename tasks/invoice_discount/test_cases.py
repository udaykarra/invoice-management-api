"""Deterministic public and hidden evaluation test suites for invoice_discount."""

from decimal import Decimal

from tasks.invoice_discount.contract import DiscountType, LineItem

PUBLIC_TEST_CASES = [
    {
        "name": "Public: Standard 10% Percentage Discount with Tax",
        "items": [
            LineItem(description="Pro License", quantity=2, unit_price=Decimal("100.00")),
        ],
        "tax_rate": "0.1000",
        "discount_type": DiscountType.PERCENTAGE,
        "discount_value": "0.1000",
        "expected_subtotal": Decimal("200.00"),
        "expected_discount": Decimal("20.00"),
        "expected_discounted_subtotal": Decimal("180.00"),
        "expected_tax": Decimal("18.00"),
        "expected_total": Decimal("198.00"),
    },
    {
        "name": "Public: Fixed Dollar Discount ($25.00)",
        "items": [
            LineItem(description="Server", quantity=1, unit_price=Decimal("150.00")),
        ],
        "tax_rate": "0.0800",
        "discount_type": DiscountType.FIXED,
        "discount_value": "25.00",
        "expected_subtotal": Decimal("150.00"),
        "expected_discount": Decimal("25.00"),
        "expected_discounted_subtotal": Decimal("125.00"),
        "expected_tax": Decimal("10.00"),
        "expected_total": Decimal("135.00"),
    },
    {
        "name": "Public: Fixed Discount Exceeding Subtotal (Capped at Subtotal)",
        "items": [
            LineItem(description="Low-cost Item", quantity=1, unit_price=Decimal("30.00")),
        ],
        "tax_rate": "0.1000",
        "discount_type": DiscountType.FIXED,
        "discount_value": "50.00",
        "expected_subtotal": Decimal("30.00"),
        "expected_discount": Decimal("30.00"),
        "expected_discounted_subtotal": Decimal("0.00"),
        "expected_tax": Decimal("0.00"),
        "expected_total": Decimal("0.00"),
    },
    {
        "name": "Public: No Discount Applied (None)",
        "items": [
            LineItem(description="Basic Item", quantity=3, unit_price=Decimal("20.00")),
        ],
        "tax_rate": "0.0500",
        "discount_type": None,
        "discount_value": None,
        "expected_subtotal": Decimal("60.00"),
        "expected_discount": Decimal("0.00"),
        "expected_discounted_subtotal": Decimal("60.00"),
        "expected_tax": Decimal("3.00"),
        "expected_total": Decimal("63.00"),
    },
]

HIDDEN_EVALUATION_TEST_CASES = [
    {
        "name": "Hidden: Commercial Rounding on Fractional Discount Cents (15.5% on $33.33)",
        # 33.33 * 0.155 = 5.16615 -> ROUND_HALF_UP rounds to 5.17
        # Discounted subtotal: 33.33 - 5.17 = 28.16
        # Tax at 7.25%: 28.16 * 0.0725 = 2.0416 -> rounds to 2.04
        # Total: 28.16 + 2.04 = 30.20
        "items": [
            LineItem(description="Service A", quantity=1, unit_price=Decimal("33.33")),
        ],
        "tax_rate": "0.0725",
        "discount_type": DiscountType.PERCENTAGE,
        "discount_value": "0.1550",
        "expected_subtotal": Decimal("33.33"),
        "expected_discount": Decimal("5.17"),
        "expected_discounted_subtotal": Decimal("28.16"),
        "expected_tax": Decimal("2.04"),
        "expected_total": Decimal("30.20"),
    },
    {
        "name": "Hidden: Zero Subtotal with Percentage Discount",
        "items": [],
        "tax_rate": "0.2000",
        "discount_type": DiscountType.PERCENTAGE,
        "discount_value": "0.5000",
        "expected_subtotal": Decimal("0.00"),
        "expected_discount": Decimal("0.00"),
        "expected_discounted_subtotal": Decimal("0.00"),
        "expected_tax": Decimal("0.00"),
        "expected_total": Decimal("0.00"),
    },
    {
        "name": "Hidden: 100% Percentage Discount",
        "items": [
            LineItem(description="Full Coupon", quantity=2, unit_price=Decimal("49.99")),
        ],
        "tax_rate": "0.1000",
        "discount_type": DiscountType.PERCENTAGE,
        "discount_value": "1.0000",
        "expected_subtotal": Decimal("99.98"),
        "expected_discount": Decimal("99.98"),
        "expected_discounted_subtotal": Decimal("0.00"),
        "expected_tax": Decimal("0.00"),
        "expected_total": Decimal("0.00"),
    },
]

MALFORMED_TEST_CASES = [
    {
        "name": "Negative Discount Value Rejection",
        "items": [LineItem(description="Item", quantity=1, unit_price=Decimal("50.00"))],
        "tax_rate": "0.1000",
        "discount_type": DiscountType.PERCENTAGE,
        "discount_value": "-0.10",
        "expected_error": ValueError,
    },
    {
        "name": "Percentage Discount Exceeding 100% Rejection",
        "items": [LineItem(description="Item", quantity=1, unit_price=Decimal("50.00"))],
        "tax_rate": "0.1000",
        "discount_type": DiscountType.PERCENTAGE,
        "discount_value": "1.5000",
        "expected_error": ValueError,
    },
    {
        "name": "Fixed Discount Scale Exceeding Two Decimals (10.999)",
        "items": [LineItem(description="Item", quantity=1, unit_price=Decimal("50.00"))],
        "tax_rate": "0.1000",
        "discount_type": DiscountType.FIXED,
        "discount_value": "10.999",
        "expected_error": ValueError,
    },
    {
        "name": "Unsupported Discount Type String",
        "items": [LineItem(description="Item", quantity=1, unit_price=Decimal("50.00"))],
        "tax_rate": "0.1000",
        "discount_type": "BUY_ONE_GET_ONE",
        "discount_value": "10.00",
        "expected_error": ValueError,
    },
]
