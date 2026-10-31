def risk_score(overdue_invoices: int, late_payments_6m: int,
               outstanding_amount: float, days_to_expiry: int | None):
    factors = []

    if late_payments_6m >= 2:
        factors.append({"name": "late_payments", "value": late_payments_6m,
                        "weight": 30, "contribution": 30})
    if overdue_invoices > 0:
        factors.append({"name": "outstanding_invoices", "value": overdue_invoices,
                        "weight": 25, "contribution": 25})
    if outstanding_amount > 10000:
        factors.append({"name": "high_outstanding_balance", "value": float(outstanding_amount),
                        "weight": 18, "contribution": 18})
    if days_to_expiry is not None and days_to_expiry <= 30:
        factors.append({"name": "expiry_approaching_days", "value": days_to_expiry,
                        "weight": 27, "contribution": 27})

    score = min(sum(f["contribution"] for f in factors), 100)
    band = "high" if score >= 70 else "medium" if score >= 40 else "low"
    action = {
        "high": "Contact the customer and resolve the outstanding payment before renewal",
        "medium": "Send a payment reminder",
        "low": "No action needed",
    }[band]
    return {"score": score, "band": band, "factors": factors, "action": action}