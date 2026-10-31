# Brightloop Subscriptions

**Intelligent Subscription Billing & Revenue Management Platform** — Odoo × Make-A-Ton 9.0, Kochi 2026.

> SIMULATE → VERIFY → BILL → EXPLAIN

Unifies the full recurring-revenue lifecycle:
**Products → Plans → Quotations → Subscriptions → Recurring Billing → Invoices → Payments → Revenue Analytics**

## Docs (read before coding)

| Doc | Purpose |
|---|---|
| [`docs/PROJECT_BRIEF.md`](docs/PROJECT_BRIEF.md) | Full problem statement, modules, priorities, demo plan |
| [`docs/API.md`](docs/API.md) | **Frozen API contract** — frontend mocks against this |
| [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) | Financial/date/lifecycle/Git rules everyone follows |

## Stack

- **Backend:** FastAPI · SQLAlchemy 2 · Alembic · Pydantic · JWT + RBAC
- **Frontend:** React · Vite · TypeScript · Tailwind · Recharts
- **Database:** Supabase PostgreSQL (SQLite for local dev)
- **Deploy:** Railway (API) · Vercel/Netlify (web) · Odoo API behind `ODOO_ENABLED` flag

## Quickstart (backend)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env            # then edit values — never commit .env

.venv/bin/alembic upgrade head  # schema (Alembic is the only migration authority)
.venv/bin/uvicorn app.main:app --reload   # http://127.0.0.1:8000  ·  /health

.venv/bin/python -m pytest tests/ -q       # run tests — do this before pushing
```

Admin account bootstraps automatically on startup from `ADMIN_EMAIL` / `ADMIN_PASSWORD`
(password rules apply). Public registration always creates **customer** accounts.

## Team workflow

| Branch | Owner | Scope |
|---|---|---|
| `feature/backend` | M1 (Athul) | `app/`, `alembic/`, `docs/API.md` |
| `feature/ai-engine` | M2 | `app/catalog`, `app/reporting`, `app/insights`, `app/seeds` |
| `feature/frontend` | M3 | `frontend/` |
| `feature/integration` | M4 | `tests/`, `docs/PERFORMANCE.md`, deploy config |

Conventional commits · push ≥ hourly · never force-push shared branches · `main` stays deployable.
