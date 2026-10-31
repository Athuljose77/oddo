"""MRR forecast: Holt linear trend vs a naive-last baseline, checked on a 3-month holdout.

Honest rule: Holt is only used when it beats the naive baseline on the holdout.
Otherwise the response says method = "naive_last" and confidence = "low".
Pure functions (no DB) so they are easy to test.
"""
from decimal import ROUND_HALF_UP, Decimal

HOLDOUT = 3
MIN_POINTS = 8  # need enough history to fit + backtest
ALPHAS = [i / 10 for i in range(1, 10)]
BETAS = [i / 10 for i in range(1, 10)]


def _fit(y, alpha, beta):
    """Return (sse of one-step-ahead errors, level, trend)."""
    level, trend = y[0], y[1] - y[0]
    sse = 0.0
    for v in y[1:]:
        pred = level + trend
        sse += (v - pred) ** 2
        new_level = alpha * v + (1 - alpha) * (level + trend)
        trend = beta * (new_level - level) + (1 - beta) * trend
        level = new_level
    return sse, level, trend


def holt_forecast(y, horizon):
    best = min(((_fit(y, a, b), a, b) for a in ALPHAS for b in BETAS), key=lambda t: t[0][0])
    (_, level, trend), _, _ = best
    return [max(0.0, level + h * trend) for h in range(1, horizon + 1)]


def naive_forecast(y, horizon):
    return [y[-1]] * horizon


def mae(actual, pred):
    return sum(abs(a - p) for a, p in zip(actual, pred)) / len(actual)


def backtest(y, holdout=HOLDOUT):
    train, test = y[:-holdout], y[-holdout:]
    return mae(test, holt_forecast(train, holdout)), mae(test, naive_forecast(train, holdout))


def next_months(last_month: str, n: int):
    y, m = int(last_month[:4]), int(last_month[5:7])
    out = []
    for _ in range(n):
        m += 1
        if m == 13:
            y, m = y + 1, 1
        out.append(f"{y:04d}-{m:02d}")
    return out


def q2(x):
    return Decimal(str(round(x, 2))).quantize(Decimal("0.01"), ROUND_HALF_UP)


def forecast_series(values, last_month: str, horizon: int = 3) -> dict:
    """values: monthly actual MRR, oldest first, ending at last_month ("YYYY-MM")."""
    y = [float(v) for v in values]
    months = next_months(last_month, horizon)
    note = "Projection, not collected revenue"
    if len(y) < MIN_POINTS:
        pred, method, conf = naive_forecast(y, horizon), "naive_last", "low"
        note += f". Only {len(y)} months of history, so the naive baseline is used"
    else:
        mae_h, mae_n = backtest(y)
        if mae_h < mae_n:
            pred, method = holt_forecast(y, horizon), "holt_linear"
            conf = "medium" if (mae_n - mae_h) / mae_n >= 0.15 else "low"
        else:
            pred, method, conf = naive_forecast(y, horizon), "naive_last", "low"
        note += f". 3-month holdout error: holt {mae_h:.0f} vs naive {mae_n:.0f}"
    return {"method": method, "baseline_method": "naive_last",
            "points": [{"month": m, "value": q2(v)} for m, v in zip(months, pred)],
            "confidence": conf, "note": note}
