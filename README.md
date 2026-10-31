# Brightloop Subscriptions

**Unified Subscription Billing, Lifecycle Engine & Financial Intelligence Platform**  
*Built for Odoo × Make-A-Ton 9.0 (Kochi 2026)*

> **SIMULATE → VERIFY → BILL → EXPLAIN**  
> One digital backbone that manages the full life of a subscription business: from products, pricing tiers, and proposals to recurring billing runs, automated collections, and predictive revenue intelligence.

---

## ⚡ Key Highlights & Capabilities

- 🎯 **Products, Variants & Catalog:** Multi-variant catalog support (e.g. *Brand Odoo* +₹560 surcharge), flexible billing frequencies (*daily*, *weekly*, *monthly*, *yearly*), and policy controls (*allow_pause*, *allow_renew*, *auto_close*, *allow_early_close*).
- 🧾 **Tax & Discount Rules:** Flexible percentage and fixed discount engines, regional tax rules (CGST, SGST, IGST), and automatic tax application on recurring runs.
- 📑 **Quotations & Proposals:** Template-driven proposals (*Draft* → *Sent* → *Confirmed* → *Active Subscription*) with instant downloadable PDF contracts.
- 🔄 **Autonomous Billing Engine:** Safe recurring billing with `dry_run` simulation and `live` run modes, automated multi-period catch-up, and zero-risk execution.
- 💳 **Payments & Reconciliation:** Multi-method payment capture (UPI, Card, Net Banking, Cash) with automated invoice state transitions (*unpaid* → *partial* → *paid*).
- 📈 **Predictive Financial Intelligence:**
  - **Live KPI Dashboard:** Normalized MRR, ARR, Unsettled Invoices, and Overdue Chase Receivables.
  - **Holt-Linear Statistical Projections:** 24-month revenue time-series combined with double exponential smoothing trend forecasting.
  - **Revenue Guardian (Churn Risk Intelligence):** Risk scoring engine evaluating late payment history, outstanding balances, upcoming contract expiries, and pause activity.
- 🔐 **Enterprise Auth & RBAC Isolation:** Strict role isolation (**Admin**, **Staff**, **Customer Self-Service Portal**), NIST-compliant password complexity, and single-use password reset tokens.

---

## 🏗️ Architecture & Technology Stack

| Layer | Technologies |
|---|---|
| **Backend API** | FastAPI, Python 3.14, Pydantic v2, Uvicorn |
| **ORM & Database** | SQLAlchemy 2.0, Alembic, Supabase PostgreSQL (with connection pooling) / SQLite for local tests |
| **Frontend UI** | React 19, Vite, Vanilla CSS Design System, Lucide Icons |
| **Math & Intelligence** | Holt-Linear Double Exponential Smoothing, Decimal-safe financial arithmetic |
| **Reporting & Export** | Native PDF generation (Invoices & Quotations) |

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Python 3.11+
- Node.js 18+ & npm

### 2. Backend Setup

```bash
# 1. Clone repository
git clone https://github.com/Athuljose77/oddo.git
cd oddo

# 2. Virtual environment & dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Environment configuration
cp .env.example .env
# Edit .env with your configuration (Supabase / local DB)

# 4. Database Migrations
alembic upgrade head

# 5. Start Backend Server (runs on http://localhost:8000)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive API documentation will be available at `http://localhost:8000/docs`.

### 3. Frontend Setup

```bash
cd frontend

# 1. Install dependencies
npm install

# 2. Start Vite Dev Server (runs on http://localhost:5173)
npm run dev -- --host 0.0.0.0 --port 5173
```

The frontend Vite server automatically proxies all `/api/v1` calls directly to the FastAPI backend.

---

## 👥 Demo Credentials

For testing and demonstration, use the seeded accounts:

| Role | Email | Password | Access Level |
|---|---|---|---|
| **Admin** | `admin@brightloop.io` | `Change!MeAdmin123` | Full system control, staff management, settings |
| **Staff Member 1** | `staff1@brightloop.demo` | `Demo@12345` | Operations, catalog, subscriptions, invoices, analytics |
| **Staff Member 2** | `staff2@brightloop.demo` | `Demo@12345` | Operations, catalog, quotations, collections |
| **Customer** | `customer001@brightloop.demo` | `Demo@12345` | Self-service portal, view contracts, pay invoices |

---

## 🧪 Test Suite

The project includes an exhaustive test suite covering authentication, RBAC boundaries, catalog invariants, quotation workflows, billing engine simulations, payment reconciliations, and reporting:

```bash
# Run all tests
source .venv/bin/activate
pytest tests/ -v
```

> **169 / 169 tests passing** across all modules.

---

## 🌐 Public Tunnel / Remote Sharing

To share the application externally (with judges or teammates):

```bash
# Using Cloudflare Quick Tunnel
npx cloudflared tunnel --url http://localhost:5173

# Or using LocalTunnel
npx localtunnel --port 5173
```

*Note:* `frontend/vite.config.js` is pre-configured with `allowedHosts: true` to seamlessly permit external tunnel hostnames.

---

## 📁 Repository Structure

```
├── alembic/                # Database migrations
├── app/
│   ├── admin/              # Staff & system administration
│   ├── auth/               # JWT authentication & password recovery
│   ├── billing/            # Invoices, payments, and billing engine
│   ├── catalog/            # Products, variants, plans, tax & discount rules
│   ├── core/               # Database, security, config, and pagination
│   ├── insights/           # Holt-linear forecasting & churn risk engine
│   ├── quoting/            # Quotation templates & proposal workflow
│   └── subscriptions/      # Subscription lifecycle & state machine
├── frontend/
│   ├── src/
│   │   ├── App.jsx         # Unified interface & role-based portals
│   │   ├── api.js          # API client
│   │   └── index.css       # Design tokens & responsive styles
│   └── vite.config.js      # Vite build & proxy config
├── seeds/                  # Seed scripts for catalog & historical subscriptions
├── tests/                  # 169 unit & integration tests
└── docs/                   # Full API contract & architecture specs
```

---

## 📜 License
MIT © 2026 Brightloop Subscriptions — Athul Jose & Team.
