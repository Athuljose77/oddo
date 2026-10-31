"""Anchor-based billing date math (docs/CONVENTIONS.md § billing date rules).

Rules:
- anchor_date = start_date, immutable once set.
- Every future period is computed FROM THE ANCHOR, never from a clamped
  previous date -> Jan 31 monthly bills Feb 28, then Mar 31 (no drift).
- Clamping: day -> last day of the shorter month. Leap years fall out naturally
  because we always clamp from the original anchor day (Feb 29 anchor returns
  Feb 29 in leap years).
"""
from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings

settings = get_settings()

DAILY = "daily"
WEEKLY = "weekly"
MONTHLY = "monthly"
YEARLY = "yearly"
CYCLES = (DAILY, WEEKLY, MONTHLY, YEARLY)


def today() -> date:
    return datetime.now(ZoneInfo(settings.billing_tz)).date()


def add_months(d: date, months: int) -> date:
    """Add months, clamping the day to the end of shorter months."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))


def period_start(anchor: date, cycle: str, index: int) -> date:
    """Start date of billing period `index` (0 = the anchor period itself)."""
    if index < 0:
        raise ValueError("index must be >= 0")
    if cycle == DAILY:
        return anchor + timedelta(days=index)
    if cycle == WEEKLY:
        return anchor + timedelta(days=7 * index)
    if cycle == MONTHLY:
        return add_months(anchor, index)
    if cycle == YEARLY:
        return add_months(anchor, 12 * index)
    raise ValueError(f"Unknown billing cycle: {cycle}")


def period_end(anchor: date, cycle: str, index: int) -> date:
    """Last (inclusive) day of billing period `index`."""
    return period_start(anchor, cycle, index + 1) - timedelta(days=1)


def first_index_on_or_after(anchor: date, cycle: str, target: date) -> tuple[int, date]:
    """Smallest period index whose start date is >= target -> (index, start_date).

    Used by resume (waive periods that fell inside the pause window) and by the
    billing engine's catch-up (skip directly to the first unbilled period).
    """
    if target <= anchor:
        return 0, anchor
    n = _approx_index(anchor, cycle, target)
    while period_start(anchor, cycle, n) < target:
        n += 1
    while n > 0 and period_start(anchor, cycle, n - 1) >= target:
        n -= 1
    return n, period_start(anchor, cycle, n)


def _approx_index(anchor: date, cycle: str, target: date) -> int:
    """Cheap estimate; the caller settles with at most a couple of steps."""
    if cycle == DAILY:
        return (target - anchor).days
    if cycle == WEEKLY:
        return (target - anchor).days // 7
    if cycle == MONTHLY:
        return (target.year - anchor.year) * 12 + (target.month - anchor.month)
    if cycle == YEARLY:
        return target.year - anchor.year
    raise ValueError(f"Unknown billing cycle: {cycle}")


def next_cycle_date(from_date: date, cycle: str) -> date:
    """The same calendar position one cycle later (used to extend expiry on renew)."""
    if cycle == DAILY:
        return from_date + timedelta(days=1)
    if cycle == WEEKLY:
        return from_date + timedelta(days=7)
    if cycle == MONTHLY:
        return add_months(from_date, 1)
    return add_months(from_date, 12)
