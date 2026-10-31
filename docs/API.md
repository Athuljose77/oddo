# Brightloop Subscriptions — API Contract (FROZEN)

> **Status:** FROZEN at Hour 0. Frontend mocks against this document.
> Any change must be agreed in team chat and this file updated in the same commit.
> Owner: M1 (Athul). Branch: `feature/backend`.

## Conventions

- **Base URL:** `/api/v1`
- **Content type:** `application/json` (except `GET /invoices/{id}/pdf` → `application/pdf`)
- **Auth:** `Authorization: Bearer <JWT>`
- **Dates:** ISO-8601 (`YYYY-MM-DD`), datetimes ISO-8601 with timezone
- **Money:** numbers as JSON numbers with 2-decimal precision; computed with Decimal server-side
- **Pagination:** query `page` (1-based, default 1), `page_size` (default 20, max 100)
  → response `{ "items": [...], "total": 123, "page": 1, "page_size": 20 }`
- **Errors:** `{ "detail": "<human readable>" }` with proper status code
  - `401` unauthenticated · `403` role/ownership violation · `404` not found
  - `409` invalid state transition / conflict · `422` validation error · `400` bad request

## Roles

| Role | Access |
|---|---|
| `admin` | Everything |
| `staff` | Day-to-day: quotations, subscriptions, billing, invoices, payments, reports, anomalies. **No** staff creation, **no** discount/tax rule writes |
| `customer` | Own data only (auto-scoped server-side). Self-service: view, accept own quotation, pause/resume/close own eligible subscription, download own invoice PDF, change password |

`CustomerScope` is applied server-side to every customer-accessible list/detail endpoint — the same endpoint, force-filtered by `customer_id = current_user.id`. Customers hitting another customer's ID get `404` (not `403` — no existence leaking).

---

## 1. Authentication — `/auth`

### POST `/auth/register` — public
Register always creates **customer** role. Payload has no role field.
```jsonc
// 201
{ "email": "owner@brightloop.io", "password": "Bright!Loop99", "name": "Asha" }
// →
{ "id": 1, "email": "owner@brightloop.io", "name": "Asha", "role": "customer" }
```
Errors: `409` duplicate email · `422` invalid password (min 9 chars, 1 upper, 1 lower, 1 special) or invalid email.

### POST `/auth/login` — public
```jsonc
{ "email": "owner@brightloop.io", "password": "Bright!Loop99" }
// → 200
{ "access_token": "<jwt>", "token_type": "bearer",
  "user": { "id": 1, "email": "...", "name": "Asha", "role": "customer" } }
```
Errors: `401` invalid credentials (same error for unknown email / wrong password).

### POST `/auth/forgot-password` — public
```jsonc
{ "email": "owner@brightloop.io" }
// → 200 { "detail": "If the email exists, a reset link has been sent." }
```
Always `200` (no user enumeration). Generates a single-use token, **stored hashed (SHA-256)**, expires in **60 minutes**. Mailer mode `log` prints the reset link to backend logs (demo mode).

### POST `/auth/reset-password` — public
```jsonc
{ "token": "<raw-token>", "new_password": "New!Pass123" }
// → 200 { "detail": "Password has been reset." }
```
Errors: `400` invalid/expired/already-used token.

### POST `/auth/change-password` — authenticated
```jsonc
{ "current_password": "Bright!Loop99", "new_password": "New!Pass123" }
// → 200
```
Errors: `401` wrong current password · `422` new password fails rules.

### GET `/auth/me` — authenticated
```jsonc
// → 200
{ "id": 1, "email": "...", "name": "Asha", "role": "customer" }
```

---

## 2. Administration — `/admin` (admin role only)

### GET `/admin/staff` — list staff accounts
### POST `/admin/staff` — create staff member (admin only)
```jsonc
{ "email": "rep@brightloop.io", "password": "Staff!Pass1", "name": "Ravi", "role": "staff" }
// → 201 { "id": 2, "email": "...", "name": "Ravi", "role": "staff" }
```
`role` accepted values: `staff` only (admin accounts are bootstrapped via env, never via API).
### PATCH `/admin/staff/{id}` — update (e.g. `{"is_active": false}`)

### GET `/customers` — staff+ (customer → own record only)
`?q=&page=` — name/email search, includes active subscription count.
### GET `/customers/{id}` — staff+ / self
### POST `/customers` — admin: create customer with temp password
```jsonc
{ "email": "buyer@acme.io", "password": "Temp!Pass123", "name": "Acme Ltd" }
```
### PATCH `/customers/{id}` — admin: `{"name": ..., "is_active": ...}` (deactivate, never delete)

---

## 3. Catalog — `/products`, `/plans` (writes: admin; reads: staff+)

### Products
- `GET /products` `?q=&page=&is_active=`
- `POST /products`
  ```jsonc
  { "name": "CloudPro", "type": "subscription", "sales_price": 2000.00,
    "cost_price": 800.00, "notes": "Flagship suite" }
  ```
- `GET /products/{id}` · `PATCH /products/{id}` (all fields partial)
- `GET /products/{id}/variants` · `POST /products/{id}/variants`
  ```jsonc
  { "attribute": "Brand", "value": "Odoo", "price_delta": 560.00 }
  // final price = base sales_price + price_delta
  ```
- `PATCH /variants/{id}` · `DELETE /variants/{id}`

### Plans
- `GET /plans` `?q=&status=&page=` · `GET /plans/{id}` · `PATCH /plans/{id}`
- `POST /plans`
  ```jsonc
  { "name": "Growth Monthly", "billing_cycle": "monthly", "price": 1180.00,
    "min_quantity": 1, "available_from": "2026-01-01", "available_to": "2027-12-31",
    "auto_close": true, "allow_early_close": false, "allow_pause": true, "allow_renew": true }
  ```
  `billing_cycle ∈ daily | weekly | monthly | yearly`
- `POST /plans/{id}/close` · `POST /plans/{id}/reopen` (admin)

### Taxes (writes: admin)
- `GET /tax-rules` · `POST /tax-rules` · `PATCH /tax-rules/{id}`
  ```jsonc
  { "name": "GST 18", "rate": 18.0, "product_id": null, "priority": 10,
    "tax_included": false, "is_active": true }
  ```
  `product_id = null` → global. Priority: lower number wins; product-specific beats global.
  `tax_included = true` → rate extracted from price; `false` → added on top. Fixed at creation.

### Discount rules — **writes: admin only** (staff may read)
- `GET /discount-rules` · `GET /discount-rules/{id}`
- `POST /discount-rules` · `PATCH /discount-rules/{id}`
  ```jsonc
  { "name": "SEAT-10", "type": "percentage", "value": 10.0,
    "min_purchase": null, "min_quantity": 10,
    "starts_at": "2026-10-01", "ends_at": "2026-12-31",
    "usage_limit": 100, "scope": "subscription", "product_id": null, "is_active": true }
  ```
  `type ∈ fixed | percentage` · `scope ∈ product | subscription`
  Response includes `used_count`. Eligibility (engine-side):
  `is_active ∧ starts_at ≤ today ≤ ends_at ∧ (usage_limit is null ∨ used_count < usage_limit) ∧ min met`.

---

## 4. Quotation templates — `/quote-templates` (staff+; writes admin)

- `GET /quote-templates` · `POST` · `GET /{id}` · `PATCH /{id}`
```jsonc
{ "name": "Professional Plan Offer", "validity_days": 7, "payment_terms": "Net 15",
  "lines": [ { "product_id": 1, "quantity": 10, "unit_price": 1180.00, "tax_rule_id": 1 } ] }
```

## 5. Quotations — `/quotations` (staff+; customer may accept own)

- `GET /quotations` `?status=&customer_id=&q=&valid_until_before=&page=`
- `POST /quotations` — from `{ "template_id": 5 }` (lines prefilled, editable) or from scratch
- `GET /quotations/{id}` · `PATCH /{id}` (only `draft`/`sent`)
- `POST /quotations/{id}/send` → `status: sent`, starts validity window
- `POST /quotations/{id}/confirm` → **converts to subscription, exactly once** (`subscription_id` UNIQUE)
  ```jsonc
  // 201
  { "quotation": { "id": 102, "number": "QUO-2026-0042", "status": "confirmed" },
    "subscription": { "id": 511, "number": "SUB-2026-0511", "status": "confirmed",
      "start_date": "2026-11-01", "expiry_date": null, "next_billing_date": "2026-11-01" } }
  ```
- `POST /quotations/{id}/cancel` → `cancelled`
- Expiry: lazy — `valid_until < today` reads as `expired`; confirm on expired → `409`
- `GET /quotations/{id}/pdf`

**Customer** may call `confirm` on **own** quotation only (accept flow).

---

## 6. Subscriptions — `/subscriptions`

- `GET /subscriptions` `?status=&plan_id=&customer_id=&q=&page=` (customer → own only)
- `POST /subscriptions` → `draft`
  ```jsonc
  { "customer_id": 10, "plan_id": 3, "start_date": "2026-11-01",
    "expiry_date": null, "payment_terms": "Net 30",
    "lines": [ { "product_id": 1, "variant_id": 2, "quantity": 10,
                 "unit_price": 1740.00, "tax_rule_id": 1 } ] }
  ```
  Validates: plan availability window, `min_quantity`.
- `GET /subscriptions/{id}` — includes lines + status history
- `PATCH /{id}` — only while `draft` or `quotation`

### Transitions (state-machine enforced; invalid → `409`)
`draft → quotation → confirmed → active → (paused ⇄ active) → closed`

| Endpoint | From → To | Guards |
|---|---|---|
| `POST /{id}/send` | draft → quotation | — |
| `POST /{id}/revise` | quotation → draft | — |
| `POST /{id}/confirm` | quotation → confirmed | — |
| `POST /{id}/activate` | confirmed → active | `start_date ≤ today` |
| `POST /{id}/pause` `{reason}` | active → paused | `plan.allow_pause` |
| `POST /{id}/resume` | paused → active | re-anchors `next_billing_date`, extends `expiry_date` by paused days |
| `POST /{id}/renew` `{new_expiry_date?}` | active→active or closed→active | `plan.allow_renew` |
| `POST /{id}/close` `{reason, early}` | active/paused → closed | `early=true` requires `plan.allow_early_close` |
| `POST /{id}/bill-now` | — | single-subscription billing, same guards as run |

All transitions record actor + timestamp. Customers may call `pause`/`resume`/`close`/`confirm` on **own** subscription only, with the same guards.
Closed subscriptions are never billed.

---

## 7. Billing — `/billing` (staff+)

### POST `/billing/runs` — **synchronous, HTTP 200**
```jsonc
{ "run_date": "2026-11-30", "mode": "dry_run" }   // or "live"
// → 200
{ "run_id": 88, "mode": "dry_run", "status": "completed",
  "started_at": "...", "finished_at": "...", "duration_ms": 840,
  "selected_count": 512, "created_count": 0, "skipped_count": 14, "failed_count": 0,
  "catchup": { "subscriptions": 3, "max_periods": 366 },
  "projected": { "invoices": 498, "subtotal": 418200.00, "tax": 75276.00,
                 "discount": 9400.00, "total": 484076.00 },
  "anomalies": [
    { "subscription_id": 184, "subscription_number": "SUB-2026-0184",
      "customer_name": "ABC Technologies", "previous_total": 1180.00,
      "projected_total": 1740.00, "change_amount": 560.00, "change_pct": 47.46,
      "reason": "Previous discount expired", "severity": "review",
      "action": "Review the invoice before sending" }
  ],
  "preview": [ { "subscription": "SUB-2026-0184", "period_start": "2026-11-30",
                 "period_end": "2026-12-29", "total": 1180.00,
                 "discount_rule": "SEAT-10", "reason": null } ] }
```
- **dry_run creates nothing:** no invoices, no `used_count` increments, no `next_billing_date` advance.
  It persists only the run + attempt rows (with `projected_*` values).
- **live** sets `created_count` = invoices created; `status = completed_with_errors` if any failed.
- Duplicate period insert → attempt `skipped(already_invoiced)` — never a second invoice.
- Errors: `409` another run in progress · `422` invalid `run_date`.

### Other run endpoints
- `GET /billing/runs` `?mode=&page=` · `GET /billing/runs/{id}`
- `GET /billing/runs/{id}/attempts` `?status=created|skipped|failed&page=`
  → attempt: `{ id, subscription_id, subscription_number, period_start, period_end,
     status, reason, invoice_id, projected_total, actual_total, error_message,
     retry_count, duration_ms }`
- `POST /billing/runs/{id}/retry` `{attempt_ids? }` — reprocesses **failed** attempts only;
  increments `retry_count` in place, preserves `error_message` history; idempotency-safe.
  → 200 with updated run counts.
- Abandoned runs: `status: running` older than `STALE_RUN_MINUTES` (15) are reaped to
  `interrupted` at startup / before new runs. Retry works on interrupted runs too.

**Note for frontend:** allow ≥ 60 s timeout on billing-run requests.

---

## 8. Invoices — `/invoices`

- `GET /invoices` `?status=&payment_status=&overdue=&customer_id=&subscription_id=`
  `&issued_from=&issued_to=&q=&sort=&page=`
  - `status ∈ draft | confirmed | paid | cancelled`
  - `payment_status ∈ unpaid | partial | paid | overpaid` (derived)
  - `overdue=true` → confirmed, unsettled, `due_date < today`
  - `sort=days_overdue` for the chase list
- `GET /invoices/{id}` — lines + payments + derived fields:
  ```jsonc
  { "id": 501, "number": "INV-2026-0501", "status": "confirmed",
    "payment_state": "partial", "total": 1500.00, "paid_amount": 900.00,
    "outstanding": 600.00, "is_overdue": true, ... }
  ```
- `POST /{id}/confirm` — draft → confirmed
- `POST /{id}/cancel` — only `draft` **and** zero payments (`409` otherwise)
- `POST /{id}/send` → sets `sent_at`, dispatches mailer (log mode prints link)
- `GET /{id}/pdf` → PDF, sets `last_printed_at`
- Auto: `confirmed → paid` when `paid_amount ≥ total` (inside payment tx)

Lifecycle: **Draft → Confirmed → Paid** (+ cancelled). Partial payments keep `status: confirmed`,
info carried by `payment_state`.

---

## 9. Payments — `/payments` (staff+; customer: read own invoice payments)

- `GET /payments` `?invoice_id=&method=&paid_from=&paid_to=&page=`
- `POST /payments`
  ```jsonc
  { "invoice_id": 501, "amount": 400.00, "method": "bank_transfer",
    "paid_at": "2026-11-30", "note": "Part payment, balance next week" }
  // → 201
  { "payment": { "id": 7, "invoice_id": 501, "amount": 400.00, "method": "bank_transfer" },
    "invoice": { "id": 501, "status": "confirmed", "payment_state": "partial",
                 "total": 1500.00, "paid_amount": 400.00,
                 "outstanding": 1100.00, "is_overdue": false } }
  ```
  `method ∈ bank_transfer | card | cash | upi | cheque | other`
  Errors: `422` amount ≤ 0 · `409` amount > outstanding unless `ALLOW_OVERPAYMENT=true`
  (then `payment_state: overpaid`).
- `GET /payments/{id}`

---

## 10. Reports & intelligence (staff+)

### GET `/reports/summary` `?from=&to=`
```jsonc
{ "active_subscriptions": 4821, "mrr": 612400.00,
  "revenue_collected": 418200.00, "outstanding": 96300.00,
  "overdue_count": 37, "overdue_amount": 21450.00,
  "recent_payments": [ ... last 5 ... ] }
```
### GET `/reports/mrr` `?months=24`
```jsonc
{ "current_mrr": 612400.00, "arr": 7348800.00,
  "normalization": { "daily": "price*365/12", "weekly": "price*52/12",
                     "monthly": "price", "yearly": "price/12" },
  "series": [ { "month": "2026-09", "mrr": 598000.00, "kind": "actual" },
              { "month": "2026-11", "mrr": 620500.00, "kind": "projection" } ] }
```
Excludes paused, excludes tax, net of recurring discounts. `kind` distinguishes actual vs projection.
### GET `/reports/overdue` `?page=` — chase list, sorted by days overdue

### GET `/insights/risk` `?band=low|medium|high&page=`
```jsonc
{ "items": [ { "subscription_id": 184, "customer_name": "ABC Technologies",
    "score": 82, "band": "high",
    "factors": [ { "name": "late_payments", "value": 2, "weight": 30, "contribution": 30 },
                 { "name": "outstanding_invoices", "value": 1, "weight": 25, "contribution": 25 },
                 { "name": "expiry_approaching_days", "value": 14, "weight": 27, "contribution": 27 } ],
    "action": "Contact the customer and resolve the outstanding payment before renewal" } ] }
```
Rule-based scoring is the baseline; ML only if it beats the baseline on holdout data (same response shape either way).
### GET `/insights/forecast` `?horizon=3`
```jsonc
{ "method": "holt_linear", "baseline_method": "naive_last",
  "points": [ { "month": "2026-12", "value": 631000.00 } ],
  "confidence": "medium", "note": "Projection, not collected revenue" }
```

---

## 11. Odoo integration (admin) — disabled unless `ODOO_ENABLED=true`

- `GET /odoo/status`
  ```jsonc
  { "enabled": false, "protocol": null, "database": null, "version": null,
    "reachable": false, "mode": "mock" }
  // when enabled: protocol ∈ json2 | jsonrpc | xmlrpc (auto-negotiated, cached)
  ```
  Transport preference: `POST /json/2/<model>/<method>` + `Authorization: bearer <API_KEY>` →
  fallback `POST /jsonrpc` → fallback XML-RPC `/xmlrpc/2`.
- `POST /odoo/sync` `{ "scope": "customers" | "invoices" | "all" }`
  → `{ "synced": 12, "failed": 0, "errors": [...] }`; mock mode simulates success.

---

## Mock-first workflow (M3)

1. Copy response shapes from this document into `frontend/src/mocks/*.json`.
2. Typed client hits `/api/v1/...` behind a `USE_MOCKS` flag.
3. M1 marks endpoints `✅ implemented` in the table below as they go live; flip flag per screen.

### Endpoint implementation status (updated by M1)

| Group | Status |
|---|---|
| auth (register/login/me/forgot/reset/change-password) | ✅ implemented |
| admin (staff CRUD, customers) | ✅ implemented |
| products / variants | ✅ implemented |
| plans (+ close/reopen) | ✅ implemented |
| tax-rules / discount-rules | ✅ implemented |
| quote-templates | ✅ implemented |
| quotations (list/create/patch/send/cancel) | ✅ implemented |
| quotations confirm (→ subscription) | ✅ implemented |
| quotations pdf | ⬜ returns 501 |
| subscriptions + transitions | ✅ implemented (bill-now ✅ live) |
| billing runs + attempts + retry | ✅ implemented (dry_run/live, catch-up capped, idempotent, retry in place) |
| invoices | ⬜ |
| payments | ⬜ |
| reports / insights | ⬜ |
| odoo | ⬜ (flag off) |

Notes as implemented:
- **Money is serialized as a JSON string** (`"total": "1999.00"`, `"unit_price": "999.50"`) —
  backend uses `Decimal` to guarantee exact arithmetic. Frontend: `parseFloat(x)` before
  math, and format for display (e.g. `Intl.NumberFormat`). Never add money values as strings.
- Dates are ISO `YYYY-MM-DD`; timestamps are UTC ISO-8601.
- All list endpoints return the envelope `{items, total, page, page_size}` (templates, tax and
  discount rule lists currently return bare arrays — small groups; frontend should handle both).
- `GET /customers` for a customer role returns their own record (single item), not 403.
- Quotation `status` reads `expired` lazily when `valid_until < today` (no DB write on read).
- Subscription confirm transitions (`send/revise/confirm/activate/pause/resume/renew/close`)
  are all `POST /subscriptions/{id}/{action}` returning the full subscription (with `lines`
  and `events` status history). `renew` from `active` extends expiry by one cycle when
  `new_expiry_date` is omitted; from `closed` it re-anchors `next_billing_date` forward
  (no back-billing for the closed gap). `close` while a term remains requires
  `plan.allow_early_close`; the `early` flag in the body is informational — the server
  validates against `expiry_date`.
