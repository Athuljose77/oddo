"""Document number sequences: QUO-2026-0001, SUB-2026-0001, INV-2026-0001.

One row per (prefix, year), incremented under a row lock (PostgreSQL) so
concurrent requests never receive the same number. A UNIQUE constraint on
(name, year) is the backstop; first-creation races retry once.
"""
from datetime import UTC, datetime

from sqlalchemy import Integer, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Sequence(Base):
    __tablename__ = "sequences"
    __table_args__ = (UniqueConstraint("name", "year", name="uq_sequences_name_year"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(10), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


def next_number(db, prefix: str, width: int = 4) -> str:
    """Return e.g. 'QUO-2026-0001'. Increments within the caller's transaction."""
    year = datetime.now(UTC).year
    stmt = select(Sequence).where(Sequence.name == prefix, Sequence.year == year)
    if db.get_bind().dialect.name != "sqlite":
        stmt = stmt.with_for_update()  # serialize concurrent numbering on Postgres

    row = db.scalar(stmt)
    if row is None:
        row = Sequence(name=prefix, year=year, last_value=0)
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            # Another request created this year's row first — retry once
            db.rollback()
            return next_number(db, prefix, width)

    row.last_value += 1
    db.flush()
    return f"{prefix}-{year}-{row.last_value:0{width}d}"
