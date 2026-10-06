"""Calculate discounted totals using decimal currency arithmetic."""
from decimal import Decimal, ROUND_HALF_UP


def discounted_total(subtotal: Decimal, discount_percent: Decimal) -> Decimal:
    if subtotal < 0:
        raise ValueError("Subtotal must be non-negative")
    if not Decimal("0") <= discount_percent <= Decimal("100"):
        raise ValueError("Discount must be between 0 and 100 percent")
    factor = Decimal("1") - discount_percent
    return (subtotal * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
