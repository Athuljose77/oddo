# Brightloop Frontend

React 19 + Vite dashboard for the Brightloop Subscriptions backend.

## Run locally

From this `frontend/` directory:

```bash
npm install
npm run dev
```

Vite serves on <http://localhost:5173> and proxies `/api/*` to
`http://127.0.0.1:8000` without rewriting the path. Start the FastAPI backend
from the repository root first:

```bash
../.venv/bin/alembic upgrade head
../.venv/bin/uvicorn app.main:app --reload --port 8000
```

The backend `.env` bootstraps the first admin account. Public registration on
the login screen creates customer accounts; admin/staff accounts are created by
an admin through the API.

## What is live

- **JWT Authentication:** login, registration, session restore, and role-based views (`admin`, `staff`, `customer`)
- **Subscriptions Lifecycle:** live subscriptions, plan minimum quantity, drawer details, pause/resume/close
- **Catalog & Quoting:** live plans, customers, products, and quotation PDF generation
- **Invoices & Billing Operations:** live invoices, status filtering, one-click billing runs (dry-run & live), invoice PDF downloads
- **Payment Reconciliation:** record payments with method, note, and auto-settlement to `paid` status
- **Analytics & Revenue Guardian:** live MRR & ARR from `/reports/summary`, Holt-linear forecasting, overdue chase list, and automated risk intelligence
- **Customer Portal:** customers only see their own subscriptions, invoices, and payment receipts

## Configuration

By default the client uses the relative `/api/v1` base through the Vite proxy.
For a deployed build, set the full API root:

```bash
VITE_API_BASE=https://api.example.com/api/v1 npm run build
```

## Build

```bash
npm run build
npm run lint
```
