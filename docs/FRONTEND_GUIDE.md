# Frontend Onboarding — What You Need to Know

> For M3. Everything here was verified against the live API on 2026-10-31.
> Full contract: [`docs/API.md`](API.md). Backend questions → M1 (Athul).

## 1. Run the backend locally — you do NOT need the Supabase password

`.env.example` defaults to SQLite, so this works out of the box:

```bash
cp .env.example .env        # edit JWT_SECRET to any long random string; set your own ADMIN_EMAIL/ADMIN_PASSWORD
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head          # REQUIRED — server won't start without it
.venv/bin/uvicorn app.main:app --reload # http://127.0.0.1:8000  ·  interactive docs at /docs
```

Your admin account is created automatically on first boot from `.env`
(`ADMIN_EMAIL` / `ADMIN_PASSWORD`, password needs 9+ chars, 1 upper, 1 lower, 1 special).
Log in at `POST /api/v1/auth/login` and store `access_token`; send it as
`Authorization: Bearer <token>` on every call.

Vite's `http://localhost:5173` is already in the CORS allowlist — no backend change needed.

## 2. Build these screens now (endpoints are live)

| Screen | Endpoints (API.md §) |
|---|---|
| Login / Register / Forgot password | §1 auth |
| Admin: staff management | §2 admin |
| Customers list/detail | §2 customers |
| Products + variants | §3 products |
| Plans (incl. close/reopen) | §3 plans |
| Tax rules / discount rules | §3 |
| Quotation templates | §4 |
| Quotations: create (scratch or template), patch lines, send, confirm→subscription, cancel | §5 |
| Subscriptions: list/filter/search, detail with **status history timeline**, create, edit while draft, all 8 transition buttons (send/revise/confirm/activate/pause/resume/renew/close) | §6 |
| Customer portal (login as a customer role): own quotations (accept = confirm), own subscriptions (pause/resume/close), change password | §1, §5, §6 |

## 3. Mock these for now (contract frozen, backend lands next blocks)

Build the screens against the documented shapes; wire them when the endpoints go live
(watch the status table at the bottom of API.md — M1 flips rows to ✅):

- **Billing runs** (dry-run preview, attempts, retry) — §7
- **Invoices** (list, detail, confirm/cancel/send, PDF) — §8
- **Payments** (record, list) — §9
- **Reports / insights / charts** — §10
- Quotation + invoice **PDFs** (endpoints exist, return `501`)

## 4. Wire-format gotchas (all verified on the live API)

1. **Money is a JSON string**, not a number: `"total": "1999.00"`, `"unit_price": "999.50"`.
   Use `parseFloat()` before any math; format for display with `Intl.NumberFormat`.
   (Backend uses `Decimal` — this is what keeps the accountant happy.)
2. **List envelope**: `{ items, total, page, page_size }` on list endpoints — except
   quote-templates / tax-rules / discount-rules, which return bare arrays (handle both).
3. **Errors**: always `{ "detail": "human readable message" }` — show `detail` in toasts.
   Common codes: `401` bad/expired token · `403` logged in but wrong role ·
   `404` not found **or not yours** (customers get 404, never 403, for other customers' data) ·
   `409` invalid state move or duplicate · `422` validation (bad payload).
4. **Dates** are `YYYY-MM-DD`; timestamps are UTC ISO-8601.
5. **Subscription status values**: `draft, quotation, confirmed, active, paused, closed`.
   Invalid transitions return `409` with the reason in `detail` — surface it, don't guess.
6. **Quotation confirm** returns a wrapper, not a quotation:
   `{ quotation: {...}, subscription: {...} }` — and can only succeed **once**
   (second attempt → `409`).
7. **Customer role is auto-scoped server-side**: same endpoints, force-filtered to their own
   data. Don't build client-side filtering as a "security" measure — it's already enforced;
   just render what the API returns.

## 5. Roles — what each login can see

| Role | Can do |
|---|---|
| `admin` | Everything + staff CRUD, tax/discount/plan writes |
| `staff` | Day-to-day: quotations, subscriptions, billing, invoices, reports |
| `customer` | Own data only: accept own quotation, pause/resume/close own subscription, change password |

Hide buttons by `user.role` from the login response — but remember the backend re-checks
every permission, so hidden buttons are UX, not security.
