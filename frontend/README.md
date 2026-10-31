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

- JWT login, registration, session restore and sign-out
- Live subscriptions, plans, customers and products from `/api/v1`
- Customer-scoped data for customer accounts (plans/products/customers pages
  are hidden for that role)
- Create subscription flow with plan minimum quantity and server-side pricing
- Subscription detail drawer with invoice lines and status history
- Estimated MRR / ARR and the upcoming billing schedule derived from live data
- INR formatting from backend decimal values

## Still demo data

- **Invoices & billing** — invoice endpoints are not implemented on this branch;
  the table is explicitly labelled demo data.
- **Reports / insights** — `/reports/*` and `/insights/*` are not implemented on
  this branch. Analytics computes MRR from live plan prices and excludes tax.

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
