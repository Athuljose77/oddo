"""Server-side pagination helper — the one list envelope used everywhere.

Response shape: { "items": [...], "total": n, "page": p, "page_size": s }
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def paginate(db: Session, stmt, page: int, page_size: int) -> dict:
    """`stmt` must already contain ordering (and any filters)."""
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}
