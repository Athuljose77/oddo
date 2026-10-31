# ODOO × MAKE-A-TON 9.0 — TEAM PROJECT BRIEF

## Project: Brightloop Subscriptions
### Intelligent Subscription Billing & Revenue Management Platform

**Team size:** 4 members
**Competition:** Odoo × Make-A-Ton 9.0, Kochi 2026
**Development approach:** AI-assisted development (Vibe Coding)
**Repository:** https://github.com/Athuljose77/oddo
**Development time plan:** 8 hours (verify the official hackathon portal for the actual timer)

---

## 1. PROJECT OVERVIEW

We are building a unified subscription management platform for a fictional software company called Brightloop Software.

Brightloop sells software products through recurring subscriptions. Customers pay daily, weekly, monthly or annually depending on their selected plans.

Currently, Brightloop manages its subscription business manually:

- Customer subscriptions are tracked in spreadsheets.
- Renewals are remembered manually.
- Invoices are created by employees every month.
- Payments are matched with invoices manually.
- Revenue reports are prepared at the end of each quarter.

This creates several problems:

- Missed subscription renewals.
- Incorrect invoices.
- Duplicate billing.
- Uncollected payments.
- Expired discounts being applied incorrectly.
- Difficulty tracking recurring revenue.
- No centralized financial visibility.

### Our objective

Build one platform that automates the complete subscription business lifecycle.

The complete workflow is:

**Products → Plans → Quotations → Subscriptions → Recurring Billing → Invoices → Payments → Revenue Analytics**

The application should allow administrators, employees and customers to manage subscription operations through one centralized system.

We are not simply building seven separate CRUD pages. We are building connected business workflows.

---

## 2. OUR INNOVATION

The basic subscription management functionality is expected by the problem statement.

Our differentiator should be something beyond basic subscription and invoice management.

### Main innovation: Revenue Guardian

Revenue Guardian is an intelligent billing verification and financial monitoring component.

Its purpose is to identify billing problems before incorrect invoices reach customers.

Consider a company managing 5,000 subscriptions.

Several things can go wrong:

- A subscription may accidentally be billed twice.
- A subscription may be skipped during a billing run.
- An expired discount may be applied.
- An incorrect quantity may be billed.
- A paused subscription may accidentally receive an invoice.
- A product variant may unexpectedly increase the invoice amount.
- An invoice may contain an incorrect tax calculation.

Traditional billing software records transactions.

Revenue Guardian checks whether the transactions are correct.

### Feature 1: Billing Dry Run

Before generating actual invoices, an administrator can simulate the billing process.

The system identifies subscriptions due for billing and calculates the expected invoice totals without creating invoices.

Example:

Billing Preview:

- Subscriptions due: 500
- Expected invoices: 486
- Skipped: 12
- Require review: 2

The administrator can inspect the results before confirming the actual billing run.

A dry run must not:

- Create invoices.
- Increase discount usage counts.
- Advance subscription billing dates.
- Modify actual payment or invoice data.

### Feature 2: Pre-flight Anomaly Detection

This is our proposed signature demonstration feature.

During a dry run, compare the projected invoice for each subscription against its previous billing period.

Identify unusual changes such as:

- Sudden invoice amount increases.
- Expired discount removal.
- Unexpected quantity changes.
- Product variant changes.
- Tax changes.
- Upcoming subscription expiry.

Example:

SUB-0184 — ABC Technologies

- Previous invoice: ₹1,180
- Projected invoice: ₹1,740
- Change: +47.46%
- Reason: Previous discount expired.
- Recommended action: Review the invoice before sending.

The system should explain why an anomaly was detected.

An anomaly is a warning for human review, not automatically proof of fraud.

This feature should reuse the existing dry-run calculations and not require a separate AI infrastructure.

### Feature 3: Idempotent Billing Engine

This is our most important engineering differentiator.

If a billing process runs twice, a customer must never receive duplicate invoices for the same subscription and billing period.

Enforce this at the database level using:

`UNIQUE(subscription_id, period_start)`

This is stronger than checking only in frontend or Python code.

### Feature 4: Explainable Subscription Risk Intelligence

The system should identify customers who may have payment or renewal problems.

Example:

- Customer: ABC Technologies
- Risk score: 82/100
- Reasons: Two late payments. One outstanding invoice. Subscription approaching expiry.
- Suggested action: Contact the customer and resolve the outstanding payment before renewal.

Start with transparent rule-based scoring. Introduce trained ML models only if appropriate historical data is available and the model performs better than the baseline.

### Feature 5: MRR Forecasting

MRR means Monthly Recurring Revenue.

The application should help the finance manager understand the company's recurring revenue and estimate future revenue.

Show:

- Current MRR.
- Historical MRR.
- Expected next-month MRR.
- Changes in active subscriptions.
- Revenue changes due to renewals and cancellations.

Forecasts must clearly distinguish projections from actual collected revenue.

---

## 3. USER ROLES AND PERMISSIONS

There are three user roles.

### Admin

The administrator has full control.

Can:

- Create and manage products.
- Configure product variants.
- Create subscription plans.
- Configure taxes.
- Create discount rules.
- Create staff accounts.
- Manage customers.
- Manage quotations.
- Manage subscriptions.
- Manage invoices.
- Record and monitor payments.
- Access financial reports.
- Access Revenue Guardian.
- Manage integration settings.

### Staff

Staff members handle regular business operations.

Can:

- View customers.
- Create and manage quotations.
- Manage subscriptions.
- Generate billing runs.
- View and manage invoices.
- Record payments.
- View reports.
- Review billing anomalies.

Cannot:

- Create new staff members.
- Create or modify discount rules.
- Modify restricted administrative settings.

### Customer

Customers have access only to their own data.

Can:

- Register and log in.
- View their own subscription details.
- View their invoices.
- View their payment history.
- Accept their own quotations.
- Pause or resume eligible subscriptions.
- Request or perform permitted cancellation operations.
- Download their own invoice PDFs.
- Change their password.

Cannot:

- View another customer's data.
- Create staff accounts.
- Modify product prices.
- Create discount rules.
- Access administration settings.

Every permission must be enforced in the backend, not just by hiding frontend buttons.

Public registration must always create a customer account. Admin accounts are bootstrapped securely, and staff accounts are created only by admins.

---

## 4. COMPLETE FUNCTIONAL MODULES

### MODULE 1: Authentication and User Management

Features: customer registration, login, logout, JWT authentication, password validation, password reset, role-based access control, admin-only staff creation, change password, customer data isolation.

Password rules:

- More than 8 characters.
- At least one uppercase letter.
- At least one lowercase letter.
- At least one special character.

Additional security:

- Never store plaintext passwords.
- Hash passwords securely.
- Store password reset token hashes.
- Reset links expire after 60 minutes.
- Reset tokens are single-use.

Email delivery should support SMTP when configured and a development mode that logs the reset link for demonstration.

### MODULE 2: Product Management

Admins can create products with: name, type, sales price, cost price, notes, product variants.

Example: Product CloudPro, base price ₹2,000. Variants: Standard +₹0, Odoo brand +₹560. If the customer selects the Odoo brand, final price = ₹2,560.

Variant adjustments must be configurable and stored in the database.

### MODULE 3: Subscription Plan Management

Admin can create plans with: plan name, price, billing frequency, minimum quantity, availability start date, availability end date, automatic closure setting, early closure permission, pause permission, renewal permission.

Supported billing frequencies: Daily, Weekly, Monthly, Yearly.

The system must validate whether a plan is available before creating a subscription.

### MODULE 4: Quotation Management

Sales representatives can create quotations using reusable quotation templates.

Quotation templates contain: template name, products, quantities, unit prices, applicable taxes, payment terms, validity duration.

Actual quotations are separate records from quotation templates.

Example: Template "Professional Plan Offer". Quotation QUO-2026-0001, customer ABC Technologies, validity 7 days.

Once the customer accepts the quotation, it converts into a subscription.

A quotation must not be converted twice.

### MODULE 5: Subscription Management

Each subscription must have: unique subscription number, customer, plan, start date, expiry date, payment terms, next billing date, last billing date, product lines, quantities, unit prices, taxes, line totals.

Subscription lifecycle: Draft → Quotation → Confirmed → Active → Closed. Additional state: Paused.

Support: pause, resume, renew, early closure when permitted, automatic closure when configured.

Every transition must be validated by a central backend state-machine service.

#### Pause and resume rules

When a subscription is paused:

- No new invoice should be generated.
- Its billing schedule is frozen.
- The system records the pause date and reason.

When resumed:

- Periods that began during the pause are waived.
- No invoice should be generated for those paused periods.
- The next billing date is re-anchored to the first eligible billing period.
- Expiry is extended by the paused duration.

An already billed period is not automatically refunded. Proration and refunds are outside the initial MVP.

---

## 5. RECURRING BILLING ENGINE

This is the central backend component.

Hundreds of subscriptions may become due on the same day.

The engine should:

1. Identify due subscriptions.
2. Check subscription status.
3. Exclude paused or closed subscriptions.
4. Check expiry dates.
5. Calculate the billing period.
6. Calculate product prices.
7. Apply eligible discounts.
8. Calculate taxes.
9. Generate invoices.
10. Update the next billing date.
11. Record the billing result.
12. Continue processing other subscriptions if one fails.

### Duplicate billing prevention

Database rule: `UNIQUE(subscription_id, period_start)`.

Also use: SELECT FOR UPDATE, database transactions, duplicate checks, failure isolation, safe retries.

### Billing catch-up

If the server misses multiple billing cycles, the system should catch up on overdue periods.

Use a configurable catch-up limit to avoid processing an unreasonable number of periods.

If one period fails: roll back that period, record the failure, stop advancing that subscription, allow safe retry, continue processing other subscriptions.

Each billing attempt must be associated with its billing period.

Recommended unique key: `UNIQUE(run_id, subscription_id, period_start)`.

For retries, update the failed attempt record and increment retry_count, preserving failure history where practical.

### Billing date rules

Use an immutable anchor date to calculate future billing periods.

Example: subscription begins January 31, monthly billing: January 31 → February 28 → March 31 → April 30 → May 31. During leap years, February may have 29 days.

Do not calculate each next date by repeatedly adding one month to an already-clamped date. Recalculate from the original anchor.

Timezone: Asia/Kolkata. No proration in the initial MVP.

### Billing execution

Use synchronous execution with HTTP 200 for the initial implementation.

Each subscription period should be processed inside its own transaction.

A billing run should track: selected subscriptions, created invoices, skipped periods, failed periods, processing duration, reasons for failures.

A stale-run recovery mechanism should identify runs left in the running state after a server crash. Default stale threshold: 15 minutes.

---

## 6. TAX AND DISCOUNT ENGINE

### Tax management

Admin creates tax rules. Tax rules can be: global, product-specific, priority-based.

Calculation order: Product price → Discount → Tax.

Use Python Decimal and PostgreSQL NUMERIC. Round using HALF_UP at the invoice-line level.

Tax inclusive/exclusive behaviour must be explicitly configured.

### Discount management

Only admins create discount rules.

Support: fixed discounts, percentage discounts, minimum purchase amount, minimum quantity, start date, end date, usage limits, product-specific discounts, subscription-level discounts.

The billing engine should automatically check discount eligibility.

Expired or exhausted discounts must not apply.

Discount usage must be protected against concurrent billing requests.

---

## 7. INVOICE MANAGEMENT

Each invoice contains: invoice number, customer, subscription reference, billing period, issue date, due date, product lines, quantity, unit price, taxes, discounts, subtotal, total amount, amount paid, outstanding amount.

Invoice lifecycle: Draft → Confirmed → Paid. Additional state: Cancelled.

A partially paid invoice remains confirmed.

Payment state is separately derived: Unpaid, Partial, Paid, Overpaid.

The invoice should automatically move to Paid when the full amount is settled.

Staff should be able to: confirm, send, print/download PDF, cancel eligible unpaid invoices.

Do not cancel paid or partially paid invoices without a proper reversal process.

---

## 8. PAYMENT MANAGEMENT

Payments are recorded against invoices.

Payment fields: invoice, amount, payment method, payment date, note, recorded by.

Payment methods: Bank transfer, Card, Cash, UPI, Cheque, Other.

Support multiple payment records for one invoice.

Example: Invoice total ₹10,000. First payment ₹4,000. Second payment ₹6,000. Outstanding balance becomes zero. The invoice is then marked Paid.

Default policy: reject payments exceeding the outstanding amount unless an explicit overpayment policy is configured.

Payment amount must always be greater than zero.

---

## 9. FINANCE DASHBOARD

The finance dashboard should display: active subscription count, MRR, revenue collected, outstanding amount, overdue invoice count, overdue amount, recent payments, subscription growth, revenue trends.

Add: date filters, invoice filters, subscription filters, search, pagination.

### MRR calculation

| Billing cycle | Monthly normalization |
|---|---|
| Daily | Daily price × 365 / 12 |
| Weekly | Weekly price × 52 / 12 |
| Monthly | Monthly price |
| Yearly | Annual price / 12 |

Exclude paused subscriptions. Exclude taxes from MRR. Use net recurring values after applicable recurring discounts.

ARR = MRR × 12.

Forecasted revenue must be clearly labelled as a projection.

---

## 10. TECHNOLOGY STACK

- Frontend: React, Vite, TypeScript, Tailwind CSS, Recharts
- Backend: Python, FastAPI, Pydantic, SQLAlchemy
- Database: Supabase PostgreSQL, Alembic migrations
- AI/ML: Scikit-learn when justified, Pandas, NumPy, explainable rule-based scoring as the initial baseline
- Integration: Odoo APIs, REST/JSON, HTTPX or Requests
- Tools: OpenCode, Git, GitHub, VS Code, Postman
- Deployment: FastAPI on Railway, Frontend on Vercel or Netlify, Database on Supabase

The frontend must never access Supabase directly. All application data should go through FastAPI.

Secrets must be stored in environment variables.

---

## 11. ODOO INTEGRATION

However, the organizers have not yet confirmed: Odoo instance, version, database, API credentials, available API subscription.

Therefore:

1. Build the integration behind an `ODOO_ENABLED` feature flag.
2. Keep it disabled by default.
3. Implement a mock integration for the demonstration.
4. Check organizer-provided access at the start of the event.
5. Enable real integration only when valid access is available.

For supported modern instances, prefer the External JSON-2 API:

`POST /json/2/<model>/<method>` with `Authorization: bearer YOUR_API_KEY`

Use compatible legacy integration only when required by the actual Odoo version.

Never connect directly to Odoo's PostgreSQL database unless explicitly authorized and technically required.

Odoo integration must not become a blocker for the core subscription system.

---

## 12. DATABASE DESIGN

Main database entities:

- Identity: users
- Catalog: products, product_variants, plans, tax_rules, discount_rules
- Quoting: quote_templates, quote_template_lines, quotations, quotation_lines
- Subscription: subscriptions, subscription_lines
- Billing: invoices, invoice_lines, billing_runs, billing_attempts, discount_redemptions, sequences
- Payments: payments

Important constraints: unique customer email, unique subscription number, unique quotation number, unique invoice number, unique invoice per subscription and billing period, positive payment amount, valid foreign-key relationships.

Use Alembic as the single schema migration authority. Do not use SQLAlchemy `create_all()` as a competing production migration mechanism.

---

## 13. BACKEND MODULE STRUCTURE

```
app/
    core/        config.py security.py dependencies.py
    auth/        routes.py schemas.py service.py
    catalog/     products.py variants.py plans.py taxes.py discounts.py
    quoting/     templates.py quotations.py service.py
    subscriptions/ models.py schemas.py routes.py service.py state_machine.py
    billing/     engine.py runs.py attempts.py tax_engine.py discount_engine.py invoices.py date_calculator.py
    payments/    routes.py service.py
    reporting/   routes.py queries.py
    insights/    risk.py forecast.py
    odoo/        client.py transport.py sync.py
    admin/       routes.py
    main.py
alembic/  tests/  docs/
```

Modules should remain independent and communicate through clear service interfaces.

---

## 14. API DESIGN

Base URL `/api/v1`, JWT Bearer token, JSON.

Groups: `/auth/*` (register, login, forgot-password, reset-password, change-password, me) · `/admin/staff` · `/products`, `/plans` · `/tax-rules`, `/discount-rules` · `/quotations` (+ send/confirm) · `/subscriptions` (+ pause/resume/renew/close/bill-now) · `/billing/runs` (+ attempts + retry) · `/invoices` (+ confirm/cancel/send/pdf) · `/payments` · `/reports/summary|mrr|overdue` · `/insights/risk|forecast` · `/odoo/status|sync`

All endpoints must have appropriate role and customer-ownership checks.

The frontend and backend must follow a shared API contract document (`docs/API.md`).

Frontend development should start with mock JSON responses and later connect to real backend endpoints.

---

## 15. FRONTEND STRUCTURE

Pages: Auth (login, registration, forgot/reset password) · Admin dashboard · Product management · Plan management · Quotation management · Subscription management · Billing Operations Center (preview, dry run, anomaly list, live run, history, failed attempts, retry) · Invoice management · Payment management · Revenue Guardian · Customer portal · Finance dashboard.

---

## 16. PERFORMANCE REQUIREMENTS

Test with: 5,200 subscriptions, 22,000 invoices, 20,000 payments, 24 months of historical data.

Use database indexes, pagination, server-side filtering, efficient SQL queries, aggregated reporting, avoid unnecessary queries, avoid loading all data into React.

M4 should measure and document actual dashboard/API query latency. Do not claim performance targets without benchmark results.

---

## 17. FOUR-MEMBER TEAM ALLOCATION

- **Member 1 — Athul: Technical Lead / Backend / Odoo Integration** — architecture, API contracts, authentication, JWT and RBAC, quotations, subscription lifecycle, billing engine, invoice generation, payment transaction logic, Odoo connector, Alembic migrations. First deliverable: working authentication endpoints and initial schema.
- **Member 2 — AI/ML / Data Engineer** — seed-data generator, product and plan CRUD, tax and discount configuration, reporting queries, MRR normalization, overdue and churn risk scoring, MRR forecast. First deliverable: seed generator.
- **Member 3 — Frontend Developer** — React + TypeScript, Vite, Tailwind, all screens. First deliverable: scaffold with mock-driven subscription list. Never wait for the complete backend.
- **Member 4 — Integration / QA / Deployment** — Supabase, Railway, environment configuration, smoke tests, contract tests, customer data isolation tests, performance measurements, Odoo access testing, demo preparation, documentation. First deliverable: deployed FastAPI hello-world connected to Supabase.

---

## 18. GIT WORKFLOW

Branches: `main` (stable), `feature/backend` (M1), `feature/ai-engine` (M2), `feature/frontend` (M3), `feature/integration` (M4).

Rules: everyone commits with their own GitHub account · commit frequently · push at least once every hour · keep main deployable · avoid modifying another member's files · coordinate before changing shared files · integrate continuously · test after merging · never force-push shared branches.

Commit format: `feat: implement authentication API`, `fix: prevent duplicate invoice generation`, `test: add billing engine tests`.

Every push communicated in team chat: member / branch / completed / files changed / status.

---

## 19. EIGHT-HOUR HACKATHON EXECUTION PLAN

- **Hour 0–1 Foundation:** M1 freeze API contracts, API.md, initial Alembic migration, configure backend, check Odoo access · M2 design seed generator · M3 React+TS scaffold, typed API client, mock JSON · M4 Supabase + Railway, deploy initial endpoint, env vars. Checkpoint: backend deployed, frontend scaffold running.
- **Hour 1–2 Auth:** M1 registration, login, JWT, hashing, roles · M2 generate seed data · M3 login/registration, role-based navigation · M4 smoke tests. Checkpoint: users can register and log in.
- **Hour 2–3 Catalog & quotations:** M1 templates, quotation creation, conversion · M2 product/variant/plan/tax/discount CRUD · M3 product/plan/quotation screens · M4 contract testing. Checkpoint: products, plans, quotations work.
- **Hour 3–4 Subscription lifecycle:** M1 state transitions, pause/resume, renewal, billing dates · M2 reporting queries, MRR normalization · M3 subscription list/details/buttons · M4 performance baseline. Checkpoint: complete lifecycle.
- **Hour 4–5 Billing:** M1 engine, locks, invoices, dry run, failure isolation, idempotency · M2 risk scoring · M3 Billing Operations Center, invoice screens · M4 integration testing. Checkpoint: dry run and live billing work.
- **Hour 5–6 Invoices & payments:** M1 invoice operations, payment transactions, discount redemption, retry, portal endpoints · M2 risk endpoints, forecast baseline · M3 invoice details, payment modal, overdue filters · M4 portal permission testing. Checkpoint: invoice and payment workflow works.
- **Hour 6–7 Reporting & intelligence:** M1 corrections, Odoo mock, edge cases · M2 risk intelligence, MRR forecast · M3 finance dashboard, Revenue Guardian, charts · M4 measure performance, documentation. Checkpoint: all major workflows integrated.
- **Hour 7–8 Stabilization:** everyone fixes bugs, tests workflows, permissions, duplicate protection, data isolation, deployment verification, demo rehearsal. Feature freeze ≈ 7:50.

---

## 20. PRIORITY SYSTEM

**P0 (required):** auth+RBAC · products and variants · plans · quotations and subscriptions · subscription lifecycle · recurring billing · taxes · duplicate invoice prevention · payments · finance dashboard · overdue detection.

**P1:** discount engine · customer portal · pause/resume · quotation templates · invoice sending and PDF · billing dry run · billing retry.

**P2:** pre-flight anomaly detection · explainable risk scoring · MRR forecasting · Odoo integration · large-scale performance demonstration · UI refinements.

Never sacrifice billing correctness, RBAC or customer data protection for cosmetic improvements.

---

## 21. TESTING AND ACCEPTANCE CRITERIA

Verify before presentation:

- **Auth:** duplicate email rejected · invalid password rejected · registration cannot create admin/staff · reset link works · staff creation admin-only.
- **Catalog:** products createable · variant price adjustments work · four billing frequencies · plan availability enforced.
- **Quotes/subscriptions:** templates populate lines · quotations expire correctly · accepted quotations convert only once · lifecycle rules work · pause/resume permissions work · closed subscriptions never billed.
- **Billing:** due subscriptions generate invoices · taxes correct · discounts correct · same period never twice · paused periods not charged · missed periods recovered · failed periods retried safely · dry run modifies nothing.
- **Payments:** correct invoice · multiple payments · partial balances · fully paid → Paid · overpayment policy.
- **Reporting:** counts correct · MRR normalized · outstanding correct · overdue identified · filters work · performance measured.
- **Portal:** own records only · cross-customer access blocked · self-service operations work.
- **Deployment:** frontend loads · backend reachable · DB connected · env configured · no secrets in GitHub.

---

## 22. DEMONSTRATION PLAN

1. Log in as admin. 2. Create product + variant. 3. Create plan. 4. Register/select customer. 5. Create quotation from template. 6. Confirm quotation → subscription. 7. Run Billing Dry Run. 8. Show Revenue Guardian detecting an unusual change. 9. Resolve/review the flagged issue. 10. Execute live billing run. 11. Show successful/failed/skipped attempts. 12. Demonstrate duplicate prevention by rerunning the same period. 13. Record partial payment. 14. Record remaining payment. 15. Open finance dashboard. 16. Demonstrate overdue and recurring revenue analytics.

Use seeded demonstration accounts and data. All seeded data and synthetic anomalies are test/demo data.

---

## 23. IMPORTANT TECHNICAL DECISIONS

- PostgreSQL for application data · Alembic for migrations · Decimal for financial calculations · backend-enforced permissions · JWT auth · no secrets in the frontend · optional Odoo integration · mock data for parallel development · database-level unique constraint for billing idempotency · one authoritative API contract · server-side pagination · recorded billing attempts and errors · avoid unnecessary LLM calls for financial calculations · never claim untested performance or predictive accuracy.

### Important unresolved questions (confirm with organizers)

1. Is an Odoo instance provided? 2. Which Odoo version? 3. Are API credentials available? 4. Is real Odoo integration mandatory? 5. What is the exact official hackathon time limit? 6. Any additional judging criteria or deployment requirements?

Until confirmed: keep Odoo integration disabled and use a mock fallback.

---

## 24. FINAL TEAM PRINCIPLES

1. Understand the requirements before asking AI to generate code.
2. Agree on architecture and API contracts.
3. Assign file and module ownership.
4. Develop frontend and backend in parallel.
5. Use mock API responses to unblock frontend development.
6. Commit and push regularly.
7. Test each module before integration.
8. Integrate early.
9. Prioritize a working end-to-end application.
10. Keep the final demonstration ready.

### OUR PRODUCT IN ONE SENTENCE

Brightloop Subscriptions is an intelligent subscription management platform that automates the entire recurring revenue lifecycle, protects businesses against billing errors and provides actionable financial intelligence.

### OUR SIGNATURE MESSAGE

**SIMULATE → VERIFY → BILL → EXPLAIN**

We don't just generate recurring invoices. We let businesses rehearse their billing, detect unusual changes before invoices are sent, prevent duplicate charges and understand their recurring revenue.

Our goal is to build a reliable business product, not just another AI-generated dashboard.

**Let's build something that actually works.**
