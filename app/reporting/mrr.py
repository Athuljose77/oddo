from decimal import Decimal, ROUND_HALF_UP

def monthly_amount(price: Decimal, frequency: str) -> Decimal:
    factors = {
        "daily":   Decimal(365) / Decimal(12),
        "weekly":  Decimal(52) / Decimal(12),
        "monthly": Decimal(1),
        "yearly":  Decimal(1) / Decimal(12),
    }
    return (price * factors[frequency]).quantize(Decimal("0.01"), ROUND_HALF_UP)