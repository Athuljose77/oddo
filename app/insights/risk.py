def risk_score(overdue_invoices: int, late_payments_6m: int,
               outstanding_amount: float, days_to_expiry: int | None):
    score = 0
    reasons = []

    if overdue_invoices > 0:
        score += 40
        reasons.append(f"{overdue_invoices} overdue invoice(s)")
    if late_payments_6m >= 2:
        score += 30
        reasons.append(f"{late_payments_6m} late payments in the last 6 months")
    if outstanding_amount > 10000:
        score += 15
        reasons.append("High outstanding balance")
    if days_to_expiry is not None and days_to_expiry <= 30:
        score += 15
        reasons.append("Subscription expires within 30 days")

    score = min(score, 100)
    level = "High" if score >= 70 else "Medium" if score >= 40 else "Low"
    action = {
        "High": "Contact the customer and resolve payment before renewal",
        "Medium": "Send a payment reminder",
        "Low": "No action needed",
    }[level]
    return {"score": score, "level": level, "reasons": reasons, "suggested_action": action}