"""The single source of truth for subscription state transitions.

Allowed moves (docs/API.md §6, docs/CONVENTIONS.md § lifecycle):
  draft -> quotation -> confirmed -> active <-> paused -> closed
  (+ cancel paths, renew self-loop, closed -> active renew)

Guards are evaluated HERE; routes/services never assign `status` directly.
Every rule in the problem statement lives in one place so the frontend, the
billing engine, and the reports all agree.
"""
from datetime import date

from fastapi import HTTPException, status as http_status

ALLOWED_TRANSITIONS = {
    ("draft", "quotation"),
    ("draft", "closed"),
    ("quotation", "draft"),
    ("quotation", "confirmed"),
    ("quotation", "closed"),
    ("confirmed", "active"),
    ("confirmed", "closed"),
    ("active", "paused"),
    ("active", "active"),  # renew in place
    ("active", "closed"),
    ("paused", "active"),  # resume
    ("paused", "closed"),
    ("closed", "active"),  # renew after close
}


def ensure_transition(subscription, to_status: str, plan, today: date) -> None:
    """Raise 409 unless the move is legal for this subscription + plan."""
    current = subscription.status
    if (current, to_status) not in ALLOWED_TRANSITIONS:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            f"Cannot move a subscription from '{current}' to '{to_status}'",
        )

    if to_status == "paused" and not plan.allow_pause:
        raise HTTPException(http_status.HTTP_409_CONFLICT, "Cannot pause: plan does not allow pause")

    if to_status == "active" and current == "confirmed":
        if subscription.start_date > today:
            raise HTTPException(
                http_status.HTTP_409_CONFLICT,
                f"Cannot activate: start date {subscription.start_date} is in the future",
            )

    if to_status == "active" and current in ("active", "closed"):
        # renew (self-loop or reopen)
        if not plan.allow_renew:
            raise HTTPException(http_status.HTTP_409_CONFLICT, "Cannot renew: plan does not allow renewal")


def is_early_close(subscription, today: date) -> bool:
    """Closing while a term still runs = early; no expiry set or passed = natural."""
    return subscription.expiry_date is not None and subscription.expiry_date > today


def ensure_can_close(subscription, plan, today: date) -> None:
    """Early close honours plan.allow_early_close; natural close is always free."""
    if is_early_close(subscription, today) and not plan.allow_early_close:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT, "Cannot close early: plan does not allow early closure"
        )
