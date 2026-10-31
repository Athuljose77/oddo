from app.insights.forecast import forecast_series, next_months


def test_trending_series_uses_holt():
    y = [100 + 10 * i for i in range(24)]
    r = forecast_series(y, "2026-10", 3)
    assert r["method"] == "holt_linear" and r["confidence"] == "medium"
    assert [p["month"] for p in r["points"]] == ["2026-11", "2026-12", "2027-01"]
    assert float(r["points"][0]["value"]) > y[-1]


def test_flat_series_falls_back_to_naive():
    r = forecast_series([500] * 24, "2026-10", 3)
    assert r["method"] == "naive_last" and r["confidence"] == "low"


def test_short_history_is_low_confidence():
    r = forecast_series([1, 2, 3], "2026-10", 2)
    assert r["method"] == "naive_last" and len(r["points"]) == 2


def test_month_rollover():
    assert next_months("2026-12", 2) == ["2027-01", "2027-02"]
