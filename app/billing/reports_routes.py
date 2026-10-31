"""Reports and intelligence endpoints (docs/API.md §10, staff+).

GET /reports/summary
GET /reports/mrr
GET /reports/overdue
GET /insights/risk
GET /insights/forecast
"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.billing import reports_service as svc
from app.billing.invoice_routes import _to_summary
from app.core.database import get_db
from app.core.dependencies import require_staff

router = APIRouter(prefix="/api/v1", tags=["reports"])


@router.get("/reports/summary")
def summary(
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
    _=Depends(require_staff),
):
    return svc.get_summary(db, from_date=from_date, to_date=to_date)


@router.get("/reports/mrr")
def mrr(
    months: int = Query(24, ge=1, le=60),
    db: Session = Depends(get_db),
    _=Depends(require_staff),
):
    return svc.get_mrr(db, months=months)


@router.get("/reports/overdue")
def overdue(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_staff),
):
    result = svc.get_overdue(db, page=page, page_size=page_size)
    return {**result, "items": [_to_summary(i) for i in result["items"]]}


@router.get("/insights/risk")
def risk(
    band: str | None = Query(None, pattern="^(low|medium|high)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_staff),
):
    return svc.get_risk(db, band=band, page=page, page_size=page_size)


@router.get("/insights/forecast")
def forecast(
    horizon: int = Query(3, ge=1, le=12),
    db: Session = Depends(get_db),
    _=Depends(require_staff),
):
    return svc.get_forecast(db, horizon=horizon)
