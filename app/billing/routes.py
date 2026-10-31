"""Billing run endpoints (docs/API.md §7, staff+).

POST /billing/runs is synchronous: one run at a time (409 while another is
`running`), dry_run writes no invoices. Retries reprocess failed attempts in
place and work on interrupted runs.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing import engine
from app.billing.models import BillingAttempt, BillingRun
from app.billing.schemas import (
    AttemptListOut,
    AttemptOut,
    RetryIn,
    RunCreateIn,
    RunListOut,
    RunOut,
    RunSummaryOut,
)
from app.core.database import get_db
from app.core.dependencies import require_staff
from app.core.pagination import paginate

router = APIRouter(prefix="/api/v1", tags=["billing"])


def _run_or_404(db: Session, run_id: int) -> BillingRun:
    run = db.get(BillingRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Billing run not found")
    return run


@router.post("/billing/runs", response_model=RunOut)
def create_run(
    payload: RunCreateIn,
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    return engine.run_billing(db, run_date=payload.run_date, mode=payload.mode, user=user)


@router.get("/billing/runs", response_model=RunListOut)
def list_runs(
    mode: str | None = Query(None, pattern="^(dry_run|live)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    stmt = select(BillingRun)
    if mode:
        stmt = stmt.where(BillingRun.mode == mode)
    return paginate(db, stmt.order_by(BillingRun.id.desc()), page, page_size)


@router.get("/billing/runs/{run_id}", response_model=RunOut)
def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    run = _run_or_404(db, run_id)
    return engine.build_run_response(db, run)


@router.get("/billing/runs/{run_id}/attempts", response_model=AttemptListOut)
def list_attempts(
    run_id: int,
    attempt_status: str | None = Query(None, alias="status", pattern="^(created|skipped|failed)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    _run_or_404(db, run_id)
    stmt = select(BillingAttempt).where(BillingAttempt.run_id == run_id)
    if attempt_status:
        stmt = stmt.where(BillingAttempt.status == attempt_status)
    return paginate(db, stmt.order_by(BillingAttempt.id), page, page_size)


@router.post("/billing/runs/{run_id}/retry", response_model=RunOut)
def retry_run(
    run_id: int,
    payload: RetryIn | None = None,
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    run = _run_or_404(db, run_id)
    return engine.retry_run(db, run, payload.attempt_ids if payload else None)