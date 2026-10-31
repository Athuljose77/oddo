"""Reports and insights endpoints (docs/API.md section 10). Staff and admin only."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_staff
from app.insights import risk_queries
from app.reporting import queries
from app.catalog.models import Plan  # noqa: F401  (registers models)

router = APIRouter(prefix="/api/v1", tags=["reports"])


def _jsonable(obj):
    """Money goes out as strings with 2 decimals (team convention)."""
    if isinstance(obj, Decimal):
        return f"{obj:.2f}"
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


@router.get("/reports/summary")
def reports_summary(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    return _jsonable(queries.summary(db, date_from, date_to))


@router.get("/reports/mrr")
def reports_mrr(
    months: int = Query(24, ge=1, le=60),
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    return _jsonable(queries.mrr_report(db, months, 3))


@router.get("/reports/overdue")
def reports_overdue(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    return _jsonable(queries.overdue(db, page, page_size))


@router.get("/insights/risk")
def insights_risk(
    band: str | None = Query(None, pattern="^(low|medium|high)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    return _jsonable(risk_queries.risk_list(db, band, page, page_size))


@router.get("/insights/forecast")
def insights_forecast(
    horizon: int = Query(3, ge=1, le=12),
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    return _jsonable(queries.forecast_report(db, horizon))