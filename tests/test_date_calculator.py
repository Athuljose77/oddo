"""Anchor-date billing math (docs/CONVENTIONS.md § billing date rules).

The drift tests are the heart of this file: Jan 31 must bill Feb 28 AND Mar 31 —
computing from the previous (clamped) date would give Apr 28 forever after.
"""
from datetime import date

import pytest

from app.billing.date_calculator import (
    add_months,
    first_index_on_or_after,
    next_cycle_date,
    period_end,
    period_start,
)


class TestAddMonths:
    def test_same_day_when_month_long_enough(self):
        assert add_months(date(2026, 1, 15), 1) == date(2026, 2, 15)

    def test_clamps_to_february(self):
        assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)

    def test_year_boundary(self):
        assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)

    def test_negative_months(self):
        assert add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)


class TestMonthlyNoDrift:
    """Jan 31 anchor: Feb clamps, but the anchor day RETURNS — no drift."""

    anchor = date(2026, 1, 31)

    def test_full_sequence(self):
        seq = [period_start(self.anchor, "monthly", n) for n in range(6)]
        assert seq == [
            date(2026, 1, 31),
            date(2026, 2, 28),  # clamped
            date(2026, 3, 31),  # anchor day RETURNS (drift would give 4/28 or 4/30)
            date(2026, 4, 30),  # clamped
            date(2026, 5, 31),
            date(2026, 6, 30),
        ]

    def test_period_end_is_day_before_next_start(self):
        # Period 1 (Feb): Feb 28 .. Mar 30 (Mar 31 starts period 2)
        assert period_end(self.anchor, "monthly", 1) == date(2026, 3, 30)
        assert period_end(self.anchor, "monthly", 0) == date(2026, 2, 27)


class TestYearlyLeapYear:
    def test_feb29_anchor_common_year_then_leap(self):
        anchor = date(2028, 2, 29)  # leap year
        assert period_start(anchor, "yearly", 1) == date(2029, 2, 28)  # clamped
        assert period_start(anchor, "yearly", 4) == date(2032, 2, 29)  # returns

    def test_no_drift_over_many_years(self):
        anchor = date(2028, 2, 29)
        assert period_start(anchor, "yearly", 12) == date(2040, 2, 29)


class TestWeeklyAndDaily:
    def test_weekly(self):
        anchor = date(2026, 1, 1)
        assert period_start(anchor, "weekly", 3) == date(2026, 1, 22)
        assert period_end(anchor, "weekly", 3) == date(2026, 1, 28)

    def test_daily(self):
        anchor = date(2026, 1, 1)
        assert period_start(anchor, "daily", 30) == date(2026, 1, 31)
        assert period_end(anchor, "daily", 0) == date(2026, 1, 1)  # single-day period

    def test_monthly_from_month_end_anchor(self):
        assert period_start(date(2026, 3, 31), "monthly", 1) == date(2026, 4, 30)


class TestFirstIndexOnOrAfter:
    """Resume/catch-up primitive: find the first period starting on/after a date."""

    anchor = date(2026, 1, 31)

    def test_target_before_anchor(self):
        assert first_index_on_or_after(self.anchor, "monthly", date(2025, 12, 1)) == (0, self.anchor)

    def test_target_equals_period_start(self):
        assert first_index_on_or_after(self.anchor, "monthly", date(2026, 3, 31)) == (2, date(2026, 3, 31))

    def test_target_mid_period_returns_next_start(self):
        # Feb 10 falls inside period 0 (Jan 31..Feb 27) -> next start is Feb 28
        assert first_index_on_or_after(self.anchor, "monthly", date(2026, 2, 10)) == (1, date(2026, 2, 28))

    def test_month_end_ambiguity_resolves_forward(self):
        # Feb 28 IS a period start (clamped) -> returns that exact period
        assert first_index_on_or_after(self.anchor, "monthly", date(2026, 2, 28)) == (1, date(2026, 2, 28))

    def test_daily_and_weekly(self):
        a = date(2026, 1, 1)
        assert first_index_on_or_after(a, "daily", date(2026, 1, 10)) == (9, date(2026, 1, 10))
        assert first_index_on_or_after(a, "weekly", date(2026, 1, 8)) == (1, date(2026, 1, 8))
        assert first_index_on_or_after(a, "weekly", date(2026, 1, 9)) == (2, date(2026, 1, 15))

    def test_yearly(self):
        a = date(2026, 6, 1)
        assert first_index_on_or_after(a, "yearly", date(2027, 1, 1)) == (1, date(2027, 6, 1))


class TestNextCycleDate:
    def test_all_cycles(self):
        d = date(2026, 1, 31)
        assert next_cycle_date(d, "daily") == date(2026, 2, 1)
        assert next_cycle_date(d, "weekly") == date(2026, 2, 7)
        assert next_cycle_date(d, "monthly") == date(2026, 2, 28)
        assert next_cycle_date(d, "yearly") == date(2027, 1, 31)


class TestGuards:
    def test_negative_index_rejected(self):
        with pytest.raises(ValueError):
            period_start(date(2026, 1, 1), "monthly", -1)

    def test_unknown_cycle_rejected(self):
        with pytest.raises(ValueError):
            period_start(date(2026, 1, 1), "quarterly", 1)
