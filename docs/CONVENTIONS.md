# Brightloop Subscriptions — Technical Conventions

> Companion to `docs/API.md`. Agreed at Hour 0. Owner: M1.

## Financial calculations

- All money math with Python `Decimal` and PostgreSQL `NUMERIC(12,2)`. Never float.
- Rounding: **HALF_UP at the invoice-line level**; totals = sum of rounded lines.
- Calculation order: **product price → discount → tax**.
- Tax rules: `tax_included=false` → tax added on top; `true` → extracted from price.
  Priority: lower number wins; product-specific beats global.
- Single currency (no multi-currency in MVP).

## MRR normalization (exactly these factors)

| Cycle | Monthly amount |
|---|---|
| daily | `price × 365 / 12` |
| weekly | `price × 52 / 12` |
| monthly | `price × 1` |
| yearly | `price ÷ 12` |

- Include: **active** subscriptions only (paused = 0).
- Exclude: taxes. Include: recurring discounts (net).
- `ARR = MRR × 12`. Forecasts are labelled `kind: projection`, never mixed with actuals.

## Billing date rules

- `anchor_date = start_date`, immutable. Every future `next_billing_date` is computed
  **from the anchor, not from the previous (possibly clamped) date** — this prevents drift.
- Monthly: `anchor + n months`, clamp day to month end (`calendar.monthrange`).
  Jan 31 → Feb 28 → **Mar 31** → Apr 30 → May 31. Leap years: Feb 29 when valid.
- Yearly Feb 29 anchor → Feb 28 in common years, **Feb 29 returns** in leap years.
- Weekly: `anchor + n×7 days`. Daily: `anchor + n days`.
- Periods: `period_start = next_billing_date`; `period_end = next_date − 1 day` (inclusive);
  billed in advance. `due_date = issue_date + payment_terms days`.
- Timezone: **Asia/Kolkata** (`BILLING_TZ`). Dates stored as `DATE`.
- Catch-up: bill all missed periods ≤ `run_date`, capped by `MAX_CATCHUP_PERIODS` (366).
- **No proration. No refunds** (documented non-goals).

## Subscription lifecycle

```
draft → quotation → confirmed → active ⇄ paused → closed
                              closed → active (renew, if plan.allow_renew)
```

- One central state-machine service validates every transition; invalid → `409`.
- Guards: pause needs `plan.allow_pause`; early close needs `plan.allow_early_close`;
  renew needs `plan.allow_renew`; activate needs `start_date ≤ today`.

### Pause semantics
- While paused: **no invoices, `next_billing_date` frozen**.
- On resume: periods that began during the pause are **waived (never billed)**;
  `next_billing_date` re-anchors to the first period start ≥ resume date.
- On resume: `expiry_date += paused_total_days` (customer loses no paid time).
- Already-billed period is not refunded.

## Invoice lifecycle

- Stored: `status ∈ draft | confirmed | paid | cancelled`.
- `draft → confirmed` (staff endpoint); `confirmed → paid` automatic inside the payment
  transaction when `paid_amount ≥ total`.
- Derived (SQL, never stored): `payment_state ∈ unpaid | partial | paid | overpaid`;
  `is_overdue = confirmed ∧ payment_state ∈ (unpaid, partial) ∧ due_date < today`.
- Invariants (test-enforced): `status = 'paid' ⟺ paid_amount ≥ total`
  and `paid_amount = SUM(payments.amount)`.

## Billing idempotency (do not weaken)

1. `UNIQUE(invoices.subscription_id, period_start)` — the hard guarantee.
2. `SELECT ... FOR UPDATE` on the subscription row at the start of each period tx.
3. `UNIQUE(billing_runs.status) WHERE status='running'` — one run at a time.
4. `UNIQUE(billing_attempts.run_id, subscription_id, period_start)` — one attempt per period.
5. Each subscription **period** processes in its own transaction; on failure: rollback that
   period, record `failed`, **stop advancing that subscription**, continue the run.
6. Reruns/retries are always safe — duplicates become `skipped(already_invoiced)`.

## Discount concurrency

- Within the period tx: lock rules `ORDER BY id FOR UPDATE` (sorted → no deadlocks),
  check `used_count < usage_limit`, increment, insert `discount_redemptions`
  (`UNIQUE(discount_rule_id, invoice_id)`), all in one transaction.

## Passwords & tokens

- Password: `>8` chars (min 9), ≥1 uppercase, ≥1 lowercase, ≥1 special. Hashed (bcrypt/argon2).
- Reset token: random 32 bytes; **SHA-256 hash stored**, raw sent via link; expires **60 min**;
  **single-use**.
- Public registration **always** creates `customer` — role never accepted from the client.
- Admin bootstrapped from `ADMIN_EMAIL`/`ADMIN_PASSWORD` env. Staff created by admin only.

## API / code conventions

- Base `/api/v1`; JWT bearer; list envelope `{items, total, page, page_size}`.
- Backend enforces **all** permissions; customers force-scoped server-side (other ID → `404`).
- Server-side pagination/filtering always — never return unbounded lists.
- Env-only secrets (`.env` never committed; repo is public).
- Alembic is the **only** schema migration mechanism; `create_all()` is dev-only, never deploy.
- Migrations authored by M1; schema change requests go through M1.

## Git

- `feature/backend` (M1), `feature/ai-engine` (M2), `feature/frontend` (M3), `feature/integration` (M4).
- Conventional commits, push ≥ hourly, no force-push on shared branches, `main` always deployable.

## Shared Supabase dev database

- **One Supabase project** for the whole team: local dev, deployment, seeds, perf tests.
- It is a **re-seedable dev DB, not precious data** — M2's generator may wipe and rebuild it.
- `DATABASE_URL` form: `postgresql+psycopg://...?sslmode=require` (psycopg3 driver; `+psycopg` is mandatory).
- Credentials live in each member's local `.env` and Railway env vars — **never in the repo, never in chat**.
- **Tests run on SQLite only** (`tests/conftest.py` forces it): the suite wipes all tables before
  every test and must never point at the shared Supabase database.
