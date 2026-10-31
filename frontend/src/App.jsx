import { useEffect, useMemo, useState } from "react";
import {
  LayoutDashboard,
  Layers,
  Repeat,
  Users,
  Receipt,
  ChartNoAxesCombined,
  Settings,
  Search,
  Bell,
  Plus,
  ArrowUpRight,
  ArrowDownRight,
  MoreHorizontal,
  CalendarDays,
  CreditCard,
  CircleCheck,
  Clock,
  AlertCircle,
  X,
  ChevronDown,
  Menu,
  Sparkles,
  Download,
  ArrowRight,
  Zap,
  LogOut,
  RefreshCw,
  Info,
} from "lucide-react";
import "./App.css";
import { API_BASE, api, clearToken, getToken, setToken } from "./api";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const CYCLE_LABEL = { daily: "day", weekly: "week", monthly: "month", yearly: "year" };
const PLAN_COLORS = ["starter", "pro", "enterprise"];
const PLAN_DOT_COLORS = ["#169b65", "#7ba6d5", "#f0b16b", "#c7a3e0"];
const EMPTY_DATA = { subscriptions: [], plans: [], customers: [], products: [] };

const DEMO_INVOICES = [
  { id: "INV-2026-001", customer: "Demo customer", date: "2026-10-12", amount: 49, status: "paid" },
  { id: "INV-2026-002", customer: "Demo customer", date: "2026-10-15", amount: 199, status: "paid" },
  { id: "INV-2026-003", customer: "Demo customer", date: "2026-10-18", amount: 19, status: "pending" },
  { id: "INV-2026-004", customer: "Demo customer", date: "2026-10-20", amount: 49, status: "overdue" },
];

// ---------------------------------------------------------------- helpers
function toNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function titleCase(value) {
  const text = String(value || "").replace(/_/g, " ");
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "Unknown";
}

function formatMoney(value) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(toNumber(value));
}

function parseDate(value) {
  if (!value) return null;
  const raw = String(value);
  const date = new Date(raw.length <= 10 ? `${raw}T00:00:00` : raw);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDate(value) {
  const date = parseDate(value);
  return date
    ? date.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })
    : "—";
}

function formatDateTime(value) {
  const date = parseDate(value);
  return date
    ? date.toLocaleString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
}

function formatTime(value) {
  const date = parseDate(value);
  return date ? date.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "—";
}

function monthlyFrom(price, cycle) {
  const factors = { daily: 365 / 12, weekly: 52 / 12, monthly: 1, yearly: 1 / 12 };
  return toNumber(price) * (factors[cycle] ?? 1);
}

function daysUntil(value) {
  const date = parseDate(value);
  if (!date) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((date.getTime() - today.getTime()) / 86_400_000);
}

function normalizeEvent(event) {
  return {
    id: event.id ?? `${event.to_status || event.status}-${event.created_at || event.at}`,
    status: String(event.to_status || event.status || "updated").toLowerCase(),
    note: event.note || "",
    actor: event.actor_name || event.actor?.name || "System",
    at: event.created_at || event.at || null,
  };
}

function normalizeLine(line) {
  return {
    id: line.id ?? `${line.product_id}-${line.description || line.unit_price}`,
    product: line.product?.name || line.description || "Product",
    quantity: toNumber(line.quantity),
    unitPrice: toNumber(line.unit_price),
    discount: toNumber(line.discount_amount),
    taxRate: toNumber(line.tax_rate),
    taxAmount: toNumber(line.tax_amount),
    total: toNumber(line.line_total),
  };
}

function normalizeSubscription(raw) {
  const customer = raw.customer && typeof raw.customer === "object" ? raw.customer : {};
  const plan = raw.plan && typeof raw.plan === "object" ? raw.plan : {};
  const planPrice = toNumber(plan.price ?? raw.plan_price ?? 0);
  const planCycle = plan.billing_cycle || raw.billing_cycle || "monthly";

  return {
    id: raw.id,
    number: raw.number || `SUB-${raw.id}`,
    customerId: raw.customer_id ?? customer.id ?? null,
    customer: raw.customer_name || customer.name || "Unknown customer",
    email: customer.email || raw.customer_email || "",
    plan: raw.plan_name || plan.name || "No plan",
    planId: raw.plan_id ?? plan.id ?? null,
    planPrice,
    planCycle,
    mrr: monthlyFrom(planPrice, planCycle),
    amount: toNumber(raw.total ?? raw.amount ?? 0),
    cycle: planCycle,
    status: String(raw.status || "draft").toLowerCase(),
    nextBillingDate: raw.next_billing_date || raw.date || null,
    startDate: raw.start_date || null,
    expiryDate: raw.expiry_date || null,
    paymentTerms: raw.payment_terms || null,
    lines: Array.isArray(raw.lines) ? raw.lines.map(normalizeLine) : [],
    events: Array.isArray(raw.events) ? raw.events.map(normalizeEvent) : [],
    raw,
  };
}

function normalizePlan(raw) {
  return {
    id: raw.id,
    name: raw.name || "Untitled plan",
    price: toNumber(raw.price),
    cycle: raw.billing_cycle || "monthly",
    minQuantity: Math.max(1, toNumber(raw.min_quantity ?? 1)),
    status: String(raw.status || "active").toLowerCase(),
    autoClose: Boolean(raw.auto_close),
    allowEarlyClose: Boolean(raw.allow_early_close),
    allowPause: Boolean(raw.allow_pause),
    allowRenew: Boolean(raw.allow_renew),
    availableFrom: raw.available_from || null,
    availableTo: raw.available_to || null,
  };
}

function normalizeCustomer(raw) {
  return {
    id: raw.id,
    name: raw.name || raw.email || "Customer",
    email: raw.email || "",
    joined: raw.created_at || null,
    active: raw.is_active !== false,
    role: raw.role || "customer",
  };
}

function buildBillingSchedule(subscriptions) {
  const now = new Date();
  const buckets = [];
  for (let index = 0; index < 12; index += 1) {
    const date = new Date(now.getFullYear(), now.getMonth() + index, 1);
    const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
    buckets.push({ key, label: MONTHS[date.getMonth()], count: 0 });
  }

  const lookup = new Map(buckets.map((bucket) => [bucket.key, bucket]));
  subscriptions.forEach((subscription) => {
    if (subscription.status !== "active" || !subscription.nextBillingDate) return;
    const date = parseDate(subscription.nextBillingDate);
    if (!date) return;
    const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
    const bucket = lookup.get(key);
    if (bucket) bucket.count += 1;
  });

  return buckets;
}

const STATUS_TONE = {
  active: "green",
  paid: "green",
  confirmed: "green",
  draft: "amber",
  quotation: "amber",
  paused: "amber",
  pending: "amber",
  overdue: "red",
  cancelled: "red",
  closed: "red",
  disabled: "red",
};

// ---------------------------------------------------------------- shared UI
function Status({ value }) {
  const key = String(value || "unknown").toLowerCase();
  const tone = STATUS_TONE[key] || "amber";
  const Icon = tone === "green" ? CircleCheck : tone === "red" ? AlertCircle : Clock;

  return (
    <span className={`status status-${key}`}>
      <Icon size={13} />
      {titleCase(key)}
    </span>
  );
}

function Avatar({ name, index = 0 }) {
  const colors = ["#E5F4EB", "#E9EDFF", "#FCEBDD", "#F9E6F0", "#E5F1F7"];
  const safeName = name || "?";
  const initials = safeName
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2);

  return (
    <span className="avatar" style={{ background: colors[index % colors.length] }}>
      {initials || "?"}
    </span>
  );
}

function MetricCard({ title, value, change, positive = true, icon: Icon, note }) {
  return (
    <div className="metric-card">
      <div className="metric-top">
        <span>{title}</span>
        <span className="metric-icon">
          <Icon size={19} />
        </span>
      </div>
      <h2>{value}</h2>
      <div className="metric-bottom">
        {change && (
          <span className={positive ? "trend positive" : "trend negative"}>
            {positive ? <ArrowUpRight size={15} /> : <ArrowDownRight size={15} />}
            {change}
          </span>
        )}
        <span className="muted">{note}</span>
      </div>
    </div>
  );
}

function DemoBanner({ children }) {
  return (
    <div className="banner banner-warning">
      <Info size={16} />
      <div>{children}</div>
    </div>
  );
}

function BillingScheduleChart({ subscriptions, large = false }) {
  const schedule = buildBillingSchedule(subscriptions);
  const max = Math.max(...schedule.map((bucket) => bucket.count), 1);
  const total = schedule.reduce((sum, bucket) => sum + bucket.count, 0);

  if (!total) {
    return <p className="empty-state">No upcoming billing dates in the next 12 months.</p>;
  }

  return (
    <div className={`chart${large ? " large-chart" : ""}`}>
      {schedule.map((bucket) => (
        <div className="chart-column" key={bucket.key}>
          <div
            className="chart-bar"
            style={{
              height: `${Math.max((bucket.count / max) * 100, bucket.count ? 8 : 2)}%`,
              opacity: bucket.count ? 1 : 0.25,
            }}
            title={`${bucket.label}: ${bucket.count} subscription${bucket.count === 1 ? "" : "s"}`}
          />
          <span>{bucket.label}</span>
        </div>
      ))}
    </div>
  );
}

function PlanMix({ subscriptions }) {
  const active = subscriptions.filter((subscription) => subscription.status === "active");
  const groups = new Map();

  active.forEach((subscription) => {
    const key = subscription.plan || "No plan";
    const current = groups.get(key) || { name: key, count: 0, mrr: 0 };
    current.count += 1;
    current.mrr += subscription.mrr;
    groups.set(key, current);
  });

  const rows = [...groups.values()].sort((a, b) => b.count - a.count);
  if (!rows.length) return <p className="empty-state">No active subscriptions.</p>;

  return (
    <div className="plan-mix-list">
      {rows.map((row, index) => (
        <div className="plan-mix-row" key={row.name}>
          <div className="plan-mix-name">
            <span
              className="dot"
              style={{ background: PLAN_DOT_COLORS[index % PLAN_DOT_COLORS.length] }}
            />
            {row.name}
          </div>
          <div className="plan-mix-track">
            <span
              style={{
                width: `${(row.count / active.length) * 100}%`,
                background: PLAN_DOT_COLORS[index % PLAN_DOT_COLORS.length],
              }}
            />
          </div>
          <strong>
            {row.count} · {formatMoney(row.mrr)}/mo
          </strong>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- auth
function AuthScreen({ onAuth, busy, error }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ name: "", email: "", password: "" });

  function update(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  function submit(event) {
    event.preventDefault();
    onAuth({ mode, ...form });
  }

  return (
    <div className="auth-shell">
      <aside className="auth-aside">
        <div className="auth-brand">
          <span className="brand-icon">
            <Layers size={22} />
          </span>
          brightloop<span className="brand-dot">.</span>
        </div>
        <h1>
          Every subscription,
          <br />
          one clear loop.
        </h1>
        <p>
          SIMULATE → VERIFY → BILL → EXPLAIN. Manage plans, customers and recurring
          revenue from one connected workspace.
        </p>
        <ul className="auth-points">
          <li>
            <CircleCheck size={16} /> Live data from the FastAPI backend
          </li>
          <li>
            <CircleCheck size={16} /> Role-aware access for admin, staff and customers
          </li>
          <li>
            <CircleCheck size={16} /> Decimal-safe money rendered in INR
          </li>
        </ul>
        <span className="auth-note">Odoo × Make-A-Ton 9.0 · Brightloop Subscriptions</span>
      </aside>

      <main className="auth-main">
        <div className="auth-card">
          <div className="auth-tabs">
            <button
              type="button"
              className={mode === "login" ? "selected" : ""}
              onClick={() => setMode("login")}
            >
              Sign in
            </button>
            <button
              type="button"
              className={mode === "register" ? "selected" : ""}
              onClick={() => setMode("register")}
            >
              Create account
            </button>
          </div>

          <h2>{mode === "login" ? "Welcome back" : "Create your account"}</h2>
          <p className="auth-sub">
            {mode === "login"
              ? "Sign in with your Brightloop account."
              : "Public sign-up creates a customer account. Staff accounts are created by an admin."}
          </p>

          <form onSubmit={submit}>
            {mode === "register" && (
              <label>
                Full name
                <input
                  name="name"
                  value={form.name}
                  onChange={update}
                  required
                  minLength={1}
                  placeholder="Acme Ltd"
                  autoComplete="name"
                />
              </label>
            )}
            <label>
              Email
              <input
                name="email"
                type="email"
                value={form.email}
                onChange={update}
                required
                placeholder="you@company.com"
                autoComplete="email"
              />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                value={form.password}
                onChange={update}
                required
                placeholder="••••••••"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
            </label>
            {mode === "register" && (
              <p className="auth-hint">
                9+ characters, one uppercase, one lowercase and one special character.
              </p>
            )}

            {error && (
              <div className="auth-error">
                <AlertCircle size={15} /> {error}
              </div>
            )}

            <button className="primary-button auth-submit" type="submit" disabled={busy}>
              {busy ? (
                <>
                  <RefreshCw size={15} className="spin" /> Please wait…
                </>
              ) : mode === "login" ? (
                "Sign in"
              ) : (
                "Create account"
              )}
            </button>
          </form>

          <div className="auth-foot">
            <span>
              API: <code>{API_BASE}</code>
            </span>
            <span>
              Admin accounts are bootstrapped from the backend <code>.env</code>.
            </span>
          </div>
        </div>
      </main>
    </div>
  );
}

function BootScreen() {
  return (
    <div className="boot-screen">
      <div className="brand-icon">
        <Layers size={22} />
      </div>
      <p>Connecting to Brightloop…</p>
      <RefreshCw size={18} className="spin" />
    </div>
  );
}

// ---------------------------------------------------------------- dashboard
function Dashboard({ subscriptions, customers, user, isStaff, onSelect, onRefresh, loading, lastSynced }) {
  const active = subscriptions.filter((subscription) => subscription.status === "active");
  const mrr = active.reduce((sum, subscription) => sum + subscription.mrr, 0);
  const expiring = active.filter((subscription) => {
    const days = daysUntil(subscription.expiryDate);
    return days !== null && days >= 0 && days <= 30;
  }).length;
  const customerCount = isStaff ? customers.length : user ? 1 : 0;
  const scheduleTotal = buildBillingSchedule(subscriptions).reduce(
    (sum, bucket) => sum + bucket.count,
    0,
  );

  const planGroups = new Map();
  active.forEach((subscription) => {
    const key = subscription.plan || "No plan";
    planGroups.set(key, (planGroups.get(key) || 0) + 1);
  });
  const planRows = [...planGroups.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);
  let running = 0;
  const donutGradient = planRows.length
    ? planRows
        .map(([, count], index) => {
          const start = (running / Math.max(active.length, 1)) * 100;
          running += count;
          const end = (running / Math.max(active.length, 1)) * 100;
          return `${PLAN_DOT_COLORS[index % PLAN_DOT_COLORS.length]} ${start}% ${end}%`;
        })
        .join(", ")
    : "#edf0ee 0 100%";

  const activity = subscriptions
    .flatMap((subscription) =>
      subscription.events.map((event) => ({
        ...event,
        subscription: subscription.number,
        customer: subscription.customer,
      })),
    )
    .sort((a, b) => new Date(b.at || 0) - new Date(a.at || 0))
    .slice(0, 4);

  return (
    <>
      <div className="welcome-row">
        <div>
          <h2>
            Welcome back, {user?.name?.split(" ")[0] || "there"} <span>✦</span>
          </h2>
          <p>Here is what is happening across your subscriptions.</p>
        </div>
        <button className="secondary-button" onClick={onRefresh} disabled={loading}>
          <CalendarDays size={16} /> {lastSynced ? `Synced ${formatTime(lastSynced)}` : "Refresh"}
        </button>
      </div>

      <div className="metrics-grid">
        <MetricCard
          title="Estimated MRR"
          value={formatMoney(mrr)}
          change="ex-tax"
          positive
          icon={CreditCard}
          note="active plans only"
        />
        <MetricCard
          title="Active subscriptions"
          value={active.length.toString()}
          change={`${subscriptions.length} total`}
          positive
          icon={Repeat}
          note="all statuses"
        />
        <MetricCard
          title={isStaff ? "Customers" : "Your account"}
          value={customerCount.toString()}
          change={isStaff ? "directory" : "scoped"}
          positive
          icon={Users}
          note="server-enforced"
        />
        <MetricCard
          title="Expiring soon"
          value={expiring.toString()}
          change={expiring ? "Needs review" : "All clear"}
          positive={!expiring}
          icon={ChartNoAxesCombined}
          note="next 30 days"
        />
      </div>

      <div className="dashboard-grid">
        <section className="panel revenue-panel">
          <div className="panel-heading">
            <div>
              <h3>Upcoming billing</h3>
              <p>Active subscriptions by next billing month</p>
            </div>
            <span className="sync-status">{scheduleTotal} scheduled</span>
          </div>
          <div className="revenue-summary">
            <strong>{active.length}</strong>
            <span className="muted">active subscriptions in the next 12 months</span>
          </div>
          <BillingScheduleChart subscriptions={subscriptions} />
        </section>

        <section className="panel plan-panel">
          <div className="panel-heading">
            <div>
              <h3>Plan distribution</h3>
              <p>Active subscriptions by plan</p>
            </div>
          </div>
          <div className="donut-wrap">
            <div className="donut" style={{ background: `conic-gradient(${donutGradient})` }}>
              <div className="donut-center">
                <strong>{active.length}</strong>
                <span>Active</span>
              </div>
            </div>
          </div>
          {planRows.length ? (
            <div className="legend">
              {planRows.map(([name, count], index) => (
                <div key={name}>
                  <span
                    className="dot"
                    style={{ background: PLAN_DOT_COLORS[index % PLAN_DOT_COLORS.length] }}
                  />
                  {name} <strong>{count}</strong>
                </div>
              ))}
            </div>
          ) : (
            <p className="empty-state">No active subscriptions yet.</p>
          )}
        </section>
      </div>

      <section className="panel table-panel">
        <div className="panel-heading">
          <div>
            <h3>Recent subscriptions</h3>
            <p>Newest records from the live API</p>
          </div>
          <button className="text-button" onClick={() => onSelect(null, "subscriptions")}>
            View all <ArrowRight size={15} />
          </button>
        </div>
        <SubscriptionTable subscriptions={subscriptions.slice(0, 5)} onSelect={onSelect} />
      </section>

      <div className="bottom-grid">
        <section className="panel activity-panel">
          <div className="panel-heading">
            <div>
              <h3>Recent activity</h3>
              <p>Status changes recorded by the subscription state machine</p>
            </div>
          </div>
          {activity.length ? (
            activity.map((event, index) => (
              <div className="activity-item" key={event.id || index}>
                <Avatar name={event.actor} index={index} />
                <div>
                  <strong>{event.subscription}</strong>
                  <p>
                    {event.customer} · {event.note || `moved to ${titleCase(event.status)}`}
                  </p>
                </div>
                <span>{formatDateTime(event.at)}</span>
              </div>
            ))
          ) : (
            <p className="empty-state">No status events recorded yet.</p>
          )}
        </section>

        <section className="upgrade-card">
          <span className="upgrade-icon">
            <Sparkles size={21} />
          </span>
          <h3>Live backend connected.</h3>
          <p>
            {lastSynced
              ? `Last synced at ${formatTime(lastSynced)}. Billing runs and reports are the next backend blocks.`
              : "Pull the latest subscriptions, plans and customers from FastAPI."}
          </p>
          <button onClick={onRefresh} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh workspace"} <ArrowRight size={15} />
          </button>
        </section>
      </div>
    </>
  );
}

// ---------------------------------------------------------------- tables
function SubscriptionTable({ subscriptions, onSelect }) {
  if (!subscriptions.length) return <p className="empty-state">No subscriptions found.</p>;

  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Customer</th>
            <th>Plan</th>
            <th>Amount</th>
            <th>Next billing</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {subscriptions.map((subscription, index) => (
            <tr key={subscription.id}>
              <td>
                <div className="customer-cell">
                  <Avatar name={subscription.customer} index={index} />
                  <div>
                    <strong>{subscription.customer}</strong>
                    <span>{subscription.email || subscription.number}</span>
                  </div>
                </div>
              </td>
              <td>{subscription.plan}</td>
              <td>
                <strong>{formatMoney(subscription.amount)}</strong>
                <span className="table-muted">
                  /{CYCLE_LABEL[subscription.cycle] || subscription.cycle}
                </span>
              </td>
              <td>{formatDate(subscription.nextBillingDate)}</td>
              <td>
                <Status value={subscription.status} />
              </td>
              <td>
                <button
                  className="icon-button"
                  title="View subscription"
                  onClick={() => onSelect(subscription)}
                >
                  <MoreHorizontal size={18} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SubscriptionsPage({ subscriptions, isStaff, onCreate, onSelect }) {
  const [filter, setFilter] = useState("all");
  const filters = ["all", "active", "paused", "draft", "closed"];
  const filtered =
    filter === "all" ? subscriptions : subscriptions.filter((subscription) => subscription.status === filter);

  return (
    <section className="panel full-panel">
      <div className="panel-heading page-table-heading">
        <div>
          <h3>{isStaff ? "All subscriptions" : "My subscriptions"}</h3>
          <p>
            {isStaff
              ? "Manage and monitor every recurring subscription."
              : "The backend scopes this list to your own customer account."}
          </p>
        </div>
        {isStaff && (
          <button className="primary-button" onClick={() => onCreate()}>
            <Plus size={17} /> Add subscription
          </button>
        )}
      </div>

      <div className="filter-row">
        {filters.map((status) => (
          <button
            key={status}
            className={filter === status ? "filter-tab selected" : "filter-tab"}
            onClick={() => setFilter(status)}
          >
            {titleCase(status)}
          </button>
        ))}
        <span className="filter-count">{filtered.length} subscriptions</span>
      </div>

      <SubscriptionTable subscriptions={filtered} onSelect={onSelect} />
    </section>
  );
}

// ---------------------------------------------------------------- plans
function PlansPage({ plans, subscriptions, isStaff, onCreate }) {
  if (!plans.length) {
    return (
      <section className="panel full-panel">
        <div className="panel-heading">
          <div>
            <h3>Plans & pricing</h3>
            <p>Plans are created by admins through the catalog API.</p>
          </div>
        </div>
        <p className="empty-state">No plans returned by the backend yet.</p>
      </section>
    );
  }

  return (
    <div className="plans-grid">
      {plans.map((plan, index) => {
        const activeCount = subscriptions.filter(
          (subscription) => subscription.planId === plan.id && subscription.status === "active",
        ).length;
        const color = PLAN_COLORS[index % PLAN_COLORS.length];
        const available = plan.status === "active";

        return (
          <div className={`plan-card ${color}`} key={plan.id}>
            <div className="plan-card-top">
              <span className="plan-symbol">
                <Zap size={19} />
              </span>
              <span className="plan-count">{activeCount} active</span>
            </div>
            <h3>{plan.name}</h3>
            <p>
              {titleCase(plan.cycle)} billing · minimum {plan.minQuantity}
            </p>
            <div className="plan-price">
              <strong>{formatMoney(plan.price)}</strong>
              <span>/ {CYCLE_LABEL[plan.cycle] || plan.cycle}</span>
            </div>
            <div className="plan-divider" />
            <h4>Plan rules</h4>
            <div className="feature-line">
              <CircleCheck size={16} /> {plan.allowPause ? "Pause allowed" : "Pause disabled"}
            </div>
            <div className="feature-line">
              <CircleCheck size={16} /> {plan.allowRenew ? "Renewal allowed" : "Renewal disabled"}
            </div>
            <div className="feature-line">
              <CircleCheck size={16} />{" "}
              {plan.autoClose ? "Auto-closes at expiry" : "Billing may continue after expiry"}
            </div>
            <div className="feature-line">
              <CircleCheck size={16} /> Early close{" "}
              {plan.allowEarlyClose ? "allowed" : "blocked"}
            </div>
            <p className="plan-availability">
              {plan.availableFrom || plan.availableTo
                ? `Available ${formatDate(plan.availableFrom)} – ${formatDate(plan.availableTo)}`
                : "Always available"}
            </p>
            {isStaff && (
              <button
                className="plan-action"
                onClick={() => onCreate(plan.id)}
                disabled={!available}
              >
                {available ? "Create subscription" : "Plan closed"} <ArrowRight size={15} />
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------- customers
function CustomersPage({ customers, subscriptions }) {
  if (!customers.length) {
    return (
      <section className="panel full-panel">
        <div className="panel-heading">
          <div>
            <h3>Customers</h3>
            <p>Customer accounts are created through registration or the admin API.</p>
          </div>
        </div>
        <p className="empty-state">No customer accounts returned by the backend yet.</p>
      </section>
    );
  }

  return (
    <section className="panel full-panel">
      <div className="panel-heading">
        <div>
          <h3>Customers</h3>
          <p>Directory of customer accounts and their active subscriptions.</p>
        </div>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Customer</th>
              <th>Active subscriptions</th>
              <th>Plans</th>
              <th>Joined</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {customers.map((customer, index) => {
              const customerSubs = subscriptions.filter(
                (subscription) => subscription.customerId === customer.id,
              );
              const activeSubs = customerSubs.filter(
                (subscription) => subscription.status === "active",
              );
              const plans = [...new Set(activeSubs.map((subscription) => subscription.plan))];

              return (
                <tr key={customer.id}>
                  <td>
                    <div className="customer-cell">
                      <Avatar name={customer.name} index={index} />
                      <div>
                        <strong>{customer.name}</strong>
                        <span>{customer.email}</span>
                      </div>
                    </div>
                  </td>
                  <td>{activeSubs.length}</td>
                  <td>{plans.length ? plans.join(", ") : "—"}</td>
                  <td>{formatDate(customer.joined)}</td>
                  <td>
                    <Status value={customer.active ? "active" : "disabled"} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- invoices
function InvoicesPage() {
  return (
    <section className="panel full-panel">
      <div className="panel-heading">
        <div>
          <h3>Invoices & billing</h3>
          <p>Invoice lifecycle, payments and PDF downloads land in the next backend block.</p>
        </div>
        <button className="secondary-button" disabled title="Invoices API is not implemented yet">
          <Download size={15} /> Export
        </button>
      </div>

      <div className="panel-body-padded">
        <DemoBanner>
          Invoice endpoints (<code>docs/API.md §8</code>) are not implemented on this branch
          yet. The rows below are demo data so the screen can be reviewed.
        </DemoBanner>
      </div>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Invoice</th>
              <th>Customer</th>
              <th>Date</th>
              <th>Amount</th>
              <th>Status</th>
              <th>Download</th>
            </tr>
          </thead>
          <tbody>
            {DEMO_INVOICES.map((invoice) => (
              <tr key={invoice.id}>
                <td>
                  <strong>{invoice.id}</strong>
                </td>
                <td>{invoice.customer}</td>
                <td>{formatDate(invoice.date)}</td>
                <td>
                  <strong>{formatMoney(invoice.amount)}</strong>
                </td>
                <td>
                  <Status value={invoice.status} />
                </td>
                <td>
                  <button className="icon-button" disabled title="PDF endpoint pending">
                    <Download size={17} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- analytics
function AnalyticsPage({ subscriptions }) {
  const active = subscriptions.filter((subscription) => subscription.status === "active");
  const paused = subscriptions.filter((subscription) => subscription.status === "paused");
  const mrr = active.reduce((sum, subscription) => sum + subscription.mrr, 0);

  return (
    <>
      <DemoBanner>
        <code>/reports/*</code> and <code>/insights/*</code> are not implemented on this
        branch yet. MRR here is estimated from live plan prices and excludes tax; the
        billing schedule is computed from real subscription dates.
      </DemoBanner>

      <div className="analytics-grid">
        <MetricCard
          title="Estimated MRR"
          value={formatMoney(mrr)}
          change="ex-tax"
          positive
          icon={CreditCard}
          note="from active plans"
        />
        <MetricCard
          title="Estimated ARR"
          value={formatMoney(mrr * 12)}
          change="ex-tax"
          positive
          icon={ChartNoAxesCombined}
          note="MRR × 12"
        />
        <MetricCard
          title="Active subscriptions"
          value={active.length.toString()}
          change={`${subscriptions.length} total`}
          positive
          icon={Repeat}
          note="live records"
        />
        <MetricCard
          title="Paused subscriptions"
          value={paused.length.toString()}
          change={paused.length ? "Needs review" : "None"}
          positive={!paused.length}
          icon={Clock}
          note="not billed while paused"
        />

        <section className="panel analytics-chart">
          <div className="panel-heading">
            <div>
              <h3>Upcoming billing schedule</h3>
              <p>Live active subscriptions grouped by next billing month</p>
            </div>
          </div>
          <BillingScheduleChart subscriptions={subscriptions} large />
        </section>

        <section className="panel analytics-chart">
          <div className="panel-heading">
            <div>
              <h3>Plan distribution</h3>
              <p>Active subscriptions and estimated monthly value by plan</p>
            </div>
          </div>
          <div className="analytics-plan-mix">
            <PlanMix subscriptions={subscriptions} />
          </div>
        </section>
      </div>
    </>
  );
}

// ---------------------------------------------------------------- settings
function SettingsPage({ user, roleLabel, lastSynced, loading, onRefresh, onLogout }) {
  return (
    <section className="panel settings-panel">
      <h3>Account & connection</h3>
      <p>This workspace reads live data from the FastAPI backend.</p>

      <div className="settings-row">
        <div>
          <strong>Signed in as</strong>
          <span>{user.email}</span>
        </div>
        <span className="role-badge">{roleLabel}</span>
      </div>

      <div className="settings-row">
        <div>
          <strong>API base</strong>
          <span>Every request is authenticated with your JWT.</span>
        </div>
        <code>{API_BASE}</code>
      </div>

      <div className="settings-row">
        <div>
          <strong>Live data</strong>
          <span>{lastSynced ? `Last synced at ${formatTime(lastSynced)}` : "Not synced yet"}</span>
        </div>
        <button className="secondary-button" onClick={onRefresh} disabled={loading}>
          <RefreshCw size={15} className={loading ? "spin" : ""} />{" "}
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <div className="settings-row">
        <div>
          <strong>Currency</strong>
          <span>Money is rendered from backend Decimal values.</span>
        </div>
        <span>INR (₹)</span>
      </div>

      <div className="settings-row">
        <div>
          <strong>Permissions</strong>
          <span>Backend-enforced; hidden buttons are UX only.</span>
        </div>
        <span>{roleLabel}</span>
      </div>

      <button className="secondary-button" onClick={onLogout}>
        <LogOut size={15} /> Sign out
      </button>
    </section>
  );
}

// ---------------------------------------------------------------- modals
const TODAY_ISO = new Date().toISOString().slice(0, 10);

function AddSubscriptionModal({ customers, plans, products, initialPlanId, onClose, onCreated }) {
  const availablePlans = plans.filter((plan) => plan.status === "active");
  const startingPlan =
    availablePlans.find((plan) => plan.id === Number(initialPlanId)) || availablePlans[0] || null;

  const [customerId, setCustomerId] = useState(customers[0]?.id || "");
  const [planId, setPlanId] = useState(startingPlan?.id || "");
  const [productId, setProductId] = useState(products[0]?.id || "");
  const [quantity, setQuantity] = useState(startingPlan?.minQuantity || 1);
  const [startDate, setStartDate] = useState(TODAY_ISO);
  const [paymentTerms, setPaymentTerms] = useState("Net 30");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const selectedPlan = availablePlans.find((plan) => plan.id === Number(planId));

  function changePlan(value) {
    setPlanId(value);
    const nextPlan = availablePlans.find((plan) => plan.id === Number(value));
    setQuantity(nextPlan?.minQuantity || 1);
  }

  const missing = [];
  if (!customers.length) missing.push("customers");
  if (!availablePlans.length) missing.push("active plans");
  if (!products.length) missing.push("products");

  async function submit(event) {
    event.preventDefault();
    if (missing.length) {
      setError(`Create ${missing.join(", ")} first.`);
      return;
    }
    if (Number(quantity) < (selectedPlan?.minQuantity || 1)) {
      setError(`This plan requires a minimum quantity of ${selectedPlan?.minQuantity}.`);
      return;
    }

    setBusy(true);
    setError("");
    try {
      await api.createSubscription({
        customer_id: Number(customerId),
        plan_id: Number(planId),
        start_date: startDate || undefined,
        payment_terms: paymentTerms || undefined,
        lines: [
          {
            product_id: Number(productId),
            quantity: Number(quantity),
          },
        ],
      });
      const customer = customers.find((item) => item.id === Number(customerId));
      onCreated(`Subscription created for ${customer?.name || "customer"}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="modal-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <form className="modal" onSubmit={submit}>
        <div className="modal-heading">
          <div>
            <h3>New subscription</h3>
            <p>Prices, discounts and tax are computed by the backend.</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        {missing.length > 0 && (
          <DemoBanner>
            Missing {missing.join(", ")}. Create them through the API/admin workflow
            before adding a subscription.
          </DemoBanner>
        )}

        <label>
          Customer
          <select
            value={customerId}
            onChange={(event) => setCustomerId(event.target.value)}
            required
          >
            {customers.map((customer) => (
              <option key={customer.id} value={customer.id}>
                {customer.name} · {customer.email}
              </option>
            ))}
          </select>
        </label>

        <label>
          Plan
          <select value={planId} onChange={(event) => changePlan(event.target.value)} required>
            {availablePlans.map((plan) => (
              <option key={plan.id} value={plan.id}>
                {plan.name} · {formatMoney(plan.price)}/{CYCLE_LABEL[plan.cycle] || plan.cycle}
              </option>
            ))}
          </select>
        </label>

        <label>
          Product
          <select value={productId} onChange={(event) => setProductId(event.target.value)} required>
            {products.map((product) => (
              <option key={product.id} value={product.id}>
                {product.name} · {formatMoney(product.sales_price)}
              </option>
            ))}
          </select>
        </label>

        <div className="form-grid">
          <label>
            Quantity
            <input
              type="number"
              min={selectedPlan?.minQuantity || 1}
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              required
            />
          </label>
          <label>
            Start date
            <input
              type="date"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
              required
            />
          </label>
        </div>

        <label>
          Payment terms
          <select value={paymentTerms} onChange={(event) => setPaymentTerms(event.target.value)}>
            <option value="Due on receipt">Due on receipt</option>
            <option value="Net 7">Net 7</option>
            <option value="Net 15">Net 15</option>
            <option value="Net 30">Net 30</option>
            <option value="Net 45">Net 45</option>
            <option value="Net 60">Net 60</option>
          </select>
        </label>

        {selectedPlan && (
          <p className="modal-hint">
            Plan minimum: {selectedPlan.minQuantity}. Unit price comes from the selected
            product (plus variant delta) when omitted.
          </p>
        )}

        {error && (
          <div className="auth-error">
            <AlertCircle size={15} /> {error}
          </div>
        )}

        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            Cancel
          </button>
          <button className="primary-button" type="submit" disabled={busy || missing.length > 0}>
            {busy ? (
              <>
                <RefreshCw size={15} className="spin" /> Creating…
              </>
            ) : (
              <>
                <Plus size={16} /> Create subscription
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}

function DetailItem({ label, value }) {
  return (
    <div className="detail-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SubscriptionDetailModal({ subscription, onClose }) {
  const sub = subscription;

  return (
    <div
      className="modal-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="modal detail-modal">
        <div className="modal-heading">
          <div>
            <h3>{sub.number}</h3>
            <p>
              {sub.customer} · {sub.plan}
            </p>
          </div>
          <button className="icon-button" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        <div className="detail-status">
          <Status value={sub.status} />
          <span className="muted">{sub.paymentTerms || "No payment terms"}</span>
        </div>

        <div className="detail-grid">
          <DetailItem label="Start date" value={formatDate(sub.startDate)} />
          <DetailItem label="Expiry date" value={formatDate(sub.expiryDate)} />
          <DetailItem label="Next billing" value={formatDate(sub.nextBillingDate)} />
          <DetailItem label="Plan price" value={formatMoney(sub.planPrice)} />
          <DetailItem label="Invoice total" value={formatMoney(sub.amount)} />
          <DetailItem label="Billing cycle" value={titleCase(sub.cycle)} />
        </div>

        <h4>Invoice lines</h4>
        {sub.lines.length ? (
          <div className="table-scroll">
            <table className="detail-table">
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Qty</th>
                  <th>Unit price</th>
                  <th>Discount</th>
                  <th>Tax</th>
                  <th>Line total</th>
                </tr>
              </thead>
              <tbody>
                {sub.lines.map((line) => (
                  <tr key={line.id}>
                    <td>{line.product}</td>
                    <td>{line.quantity}</td>
                    <td>{formatMoney(line.unitPrice)}</td>
                    <td>{formatMoney(line.discount)}</td>
                    <td>
                      {formatMoney(line.taxAmount)} ({line.taxRate}%)
                    </td>
                    <td>
                      <strong>{formatMoney(line.total)}</strong>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-state">No line items returned for this subscription.</p>
        )}

        <h4>Status history</h4>
        {sub.events.length ? (
          <div className="timeline">
            {sub.events.map((event, index) => (
              <div className="timeline-item" key={event.id || index}>
                <span className="timeline-dot" />
                <div>
                  <strong>{titleCase(event.status)}</strong>
                  <p>
                    {event.note || "Status updated"} · {event.actor}
                  </p>
                </div>
                <span>{formatDateTime(event.at)}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="empty-state">No status events recorded.</p>
        )}

        <div className="modal-actions">
          <button className="secondary-button" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- app
export default function App() {
  const [booting, setBooting] = useState(true);
  const [user, setUser] = useState(null);
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState("");
  const [data, setData] = useState(EMPTY_DATA);
  const [loadingData, setLoadingData] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [lastSynced, setLastSynced] = useState(null);
  const [page, setPage] = useState("dashboard");
  const [search, setSearch] = useState("");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [presetPlanId, setPresetPlanId] = useState(null);
  const [selected, setSelected] = useState(null);
  const [toast, setToast] = useState(null);

  function notify(message, tone = "success") {
    setToast({ message, tone });
  }

  function handleLogout() {
    clearToken();
    setUser(null);
    setData(EMPTY_DATA);
    setLoadingData(false);
    setBooting(false);
    setSearch("");
    setPage("dashboard");
    setCreateOpen(false);
    setPresetPlanId(null);
    setSelected(null);
    setLoadError("");
    setAuthError("");
  }

  async function refreshData(activeUser = user) {
    if (!activeUser) return;
    setLoadingData(true);
    setLoadError("");

    const errors = [];
    const staffLike = activeUser.role === "admin" || activeUser.role === "staff";
    const capture = (promise) =>
      promise.catch((error) => {
        errors.push(error);
        return null;
      });

    const [subs, plans, customers, products] = await Promise.all([
      capture(api.subscriptions()),
      staffLike ? capture(api.plans()) : Promise.resolve(null),
      capture(api.customers()),
      staffLike ? capture(api.products()) : Promise.resolve(null),
    ]);

    if (errors.some((error) => error.status === 401)) {
      handleLogout();
      return;
    }

    setData({
      subscriptions: (subs?.items || []).map(normalizeSubscription),
      plans: (plans?.items || []).map(normalizePlan),
      customers: (customers?.items || []).map(normalizeCustomer),
      products: products?.items || [],
    });
    setLastSynced(new Date());

    if (errors.length) {
      setLoadError(
        errors.length === 1
          ? errors[0].message
          : `${errors.length} requests failed — some panels may be empty.`,
      );
    }
    setLoadingData(false);
  }

  useEffect(() => {
    let cancelled = false;

    async function boot() {
      if (!getToken()) {
        setBooting(false);
        return;
      }
      try {
        const me = await api.me();
        if (cancelled) return;
        setUser(me);
        await refreshData(me);
      } catch (error) {
        if (!cancelled) {
          clearToken();
          setAuthError(error.message || "Session expired. Please sign in.");
        }
      } finally {
        if (!cancelled) setBooting(false);
      }
    }

    boot();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(null), 4200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const isStaff = user?.role === "admin" || user?.role === "staff";
  const roleLabel =
    user?.role === "admin" ? "Administrator" : user?.role === "staff" ? "Staff" : "Customer";

  const visibleSubscriptions = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return data.subscriptions;
    return data.subscriptions.filter((subscription) =>
      `${subscription.number} ${subscription.customer} ${subscription.email} ${subscription.plan} ${subscription.status}`
        .toLowerCase()
        .includes(term),
    );
  }, [data.subscriptions, search]);

  async function handleAuth({ mode, name, email, password }) {
    setAuthBusy(true);
    setAuthError("");
    try {
      if (mode === "register") {
        await api.register({ name, email, password });
      }
      const result = await api.login(email, password);
      setToken(result.access_token);
      setUser(result.user);
      await refreshData(result.user);
      setPage("dashboard");
      notify(mode === "register" ? "Account created — welcome!" : `Welcome back, ${result.user.name}`);
    } catch (error) {
      setAuthError(error.message);
    } finally {
      setAuthBusy(false);
    }
  }

  async function handleCreated(message) {
    setCreateOpen(false);
    setPresetPlanId(null);
    await refreshData(user);
    notify(message || "Subscription created");
  }

  function openCreate(planId = null) {
    setPresetPlanId(planId);
    setCreateOpen(true);
  }

  function navigate(id) {
    setPage(id);
    setMobileOpen(false);
    setSelected(null);
  }

  function handleSelect(subscription, destination) {
    if (destination) {
      setPage(destination);
      return;
    }
    setSelected(subscription);
  }

  if (booting) return <BootScreen />;
  if (!user) {
    return <AuthScreen onAuth={handleAuth} busy={authBusy} error={authError} />;
  }

  const navGroups = [
    {
      title: "WORKSPACE",
      items: [
        { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
        {
          id: "subscriptions",
          label: isStaff ? "Subscriptions" : "My subscriptions",
          icon: Repeat,
        },
        ...(isStaff
          ? [
              { id: "plans", label: "Plans & Pricing", icon: Layers },
              { id: "customers", label: "Customers", icon: Users },
              { id: "invoices", label: "Invoices & Billing", icon: Receipt },
            ]
          : []),
      ],
    },
    ...(isStaff
      ? [
          {
            title: "INSIGHTS",
            items: [{ id: "analytics", label: "Analytics", icon: ChartNoAxesCombined }],
          },
        ]
      : []),
  ];

  const pageTitles = {
    dashboard: "Dashboard",
    subscriptions: isStaff ? "Subscriptions" : "My subscriptions",
    plans: "Plans & Pricing",
    customers: "Customers",
    invoices: "Invoices & Billing",
    analytics: "Analytics",
    settings: "Settings",
  };

  return (
    <div className="app-shell">
      {mobileOpen && <div className="mobile-backdrop" onClick={() => setMobileOpen(false)} />}

      <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
        <div className="brand">
          <div className="brand-icon">
            <Layers size={21} />
          </div>
          <span>
            brightloop<span className="brand-dot">.</span>
          </span>
          <button className="mobile-close icon-button" onClick={() => setMobileOpen(false)}>
            <X size={20} />
          </button>
        </div>

        <div className="workspace-switch">
          <div className="workspace-avatar">B</div>
          <div>
            <strong>Brightloop Workspace</strong>
            <span>{roleLabel}</span>
          </div>
          <ChevronDown size={16} />
        </div>

        <nav>
          {navGroups.map((group) => (
            <div className="nav-group" key={group.title}>
              <span className="nav-heading">{group.title}</span>
              {group.items.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    className={`nav-item ${page === item.id ? "active" : ""}`}
                    onClick={() => navigate(item.id)}
                  >
                    <Icon size={18} />
                    <span>{item.label}</span>
                    {item.id === "subscriptions" && (
                      <span className="nav-badge">{data.subscriptions.length}</span>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="help-card">
            <Sparkles size={18} />
            <strong>Live workspace</strong>
            <p>
              {isStaff
                ? "Data is loaded from the FastAPI backend. Admin and staff accounts see the full workspace."
                : "Your customer account only sees subscriptions scoped to you by the backend."}
            </p>
            <button onClick={() => navigate("settings")}>
              Connection settings <ArrowRight size={14} />
            </button>
          </div>
          <button
            className={`nav-item ${page === "settings" ? "active" : ""}`}
            onClick={() => navigate("settings")}
          >
            <Settings size={18} /> Settings
          </button>
          <div className="profile">
            <Avatar name={user.name} />
            <div>
              <strong>{user.name}</strong>
              <span>{roleLabel}</span>
            </div>
            <button
              className="icon-button profile-logout"
              onClick={handleLogout}
              title="Sign out"
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <button className="mobile-menu icon-button" onClick={() => setMobileOpen(true)}>
              <Menu size={21} />
            </button>
            <span className="breadcrumb">
              Workspace <span>/</span> <strong>{pageTitles[page] || "Dashboard"}</strong>
            </span>
          </div>
          <div className="topbar-right">
            {(page === "dashboard" || page === "subscriptions") && (
              <div className="search-box">
                <Search size={17} />
                <input
                  placeholder="Search subscriptions..."
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
                <kbd>⌘ K</kbd>
              </div>
            )}
            <button
              className="icon-button"
              title="Refresh live data"
              onClick={() => refreshData(user)}
              disabled={loadingData}
            >
              <RefreshCw size={18} className={loadingData ? "spin" : ""} />
            </button>
            <button
              className="notification-button"
              title="Notifications are not wired up yet"
              onClick={() => notify("Notifications are not wired up yet.")}
            >
              <Bell size={19} />
              <i />
            </button>
            <Avatar name={user.name} />
          </div>
        </header>

        <div className="page-content">
          {loadingData && (
            <div className="banner banner-info">
              <RefreshCw size={16} className="spin" />
              <div>Refreshing live data…</div>
            </div>
          )}
          {loadError && (
            <div className="banner banner-error">
              <AlertCircle size={16} />
              <div>{loadError}</div>
              <button onClick={() => refreshData(user)}>Retry</button>
            </div>
          )}

          {page === "dashboard" && (
            <Dashboard
              subscriptions={data.subscriptions}
              customers={data.customers}
              user={user}
              isStaff={isStaff}
              onSelect={handleSelect}
              onRefresh={() => refreshData(user)}
              loading={loadingData}
              lastSynced={lastSynced}
            />
          )}
          {page === "subscriptions" && (
            <SubscriptionsPage
              subscriptions={visibleSubscriptions}
              isStaff={isStaff}
              onCreate={openCreate}
              onSelect={handleSelect}
            />
          )}
          {page === "plans" && (
            <PlansPage
              plans={data.plans}
              subscriptions={data.subscriptions}
              isStaff={isStaff}
              onCreate={openCreate}
            />
          )}
          {page === "customers" && (
            <CustomersPage customers={data.customers} subscriptions={data.subscriptions} />
          )}
          {page === "invoices" && <InvoicesPage />}
          {page === "analytics" && <AnalyticsPage subscriptions={data.subscriptions} />}
          {page === "settings" && (
            <SettingsPage
              user={user}
              roleLabel={roleLabel}
              lastSynced={lastSynced}
              loading={loadingData}
              onRefresh={() => refreshData(user)}
              onLogout={handleLogout}
            />
          )}

          <footer>© 2026 Brightloop Subscriptions · Odoo × Make-A-Ton 9.0</footer>
        </div>
      </main>

      {createOpen && isStaff && (
        <AddSubscriptionModal
          customers={data.customers}
          plans={data.plans}
          products={data.products}
          initialPlanId={presetPlanId}
          onClose={() => {
            setCreateOpen(false);
            setPresetPlanId(null);
          }}
          onCreated={handleCreated}
        />
      )}

      {selected && (
        <SubscriptionDetailModal subscription={selected} onClose={() => setSelected(null)} />
      )}

      {toast && (
        <div className={`toast toast-${toast.tone}`}>
          {toast.tone === "error" ? <AlertCircle size={16} /> : <CircleCheck size={16} />}
          {toast.message}
        </div>
      )}
    </div>
  );
}
