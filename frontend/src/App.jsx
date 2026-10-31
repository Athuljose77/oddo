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
  Play,
  Send,
  Check,
  DollarSign,
  ShieldAlert,
  FileText,
  TrendingUp,
  Pause,
  Tag,
  Percent,
  Trash2,
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
  const [mode, setMode] = useState("login"); // login | register | forgot | reset
  const [form, setForm] = useState({ name: "", email: "", password: "", token: "", newPassword: "" });
  const [resetNotice, setResetNotice] = useState("");
  const [resetError, setResetError] = useState("");
  const [resetBusy, setResetBusy] = useState(false);

  function update(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  function submit(event) {
    event.preventDefault();
    if (mode === "forgot") {
      handleForgotPassword();
      return;
    }
    if (mode === "reset") {
      handleResetPassword();
      return;
    }
    onAuth({ mode, ...form });
  }

  async function handleForgotPassword() {
    setResetBusy(true);
    setResetNotice("");
    setResetError("");
    try {
      await api.forgotPassword(form.email);
      setResetNotice("If this email exists, a reset link/token has been generated (check backend console logs).");
    } catch (err) {
      setResetError(err.message || "Failed to request password reset.");
    } finally {
      setResetBusy(false);
    }
  }

  async function handleResetPassword() {
    setResetBusy(true);
    setResetNotice("");
    setResetError("");
    try {
      await api.resetPassword({ token: form.token, new_password: form.newPassword });
      setResetNotice("Password reset successfully! You can now sign in.");
      setMode("login");
    } catch (err) {
      setResetError(err.message || "Failed to reset password. Invalid or expired token.");
    } finally {
      setResetBusy(false);
    }
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
              onClick={() => { setMode("login"); setResetNotice(""); setResetError(""); }}
            >
              Sign in
            </button>
            <button
              type="button"
              className={mode === "register" ? "selected" : ""}
              onClick={() => { setMode("register"); setResetNotice(""); setResetError(""); }}
            >
              Create account
            </button>
            {(mode === "forgot" || mode === "reset") && (
              <button
                type="button"
                className="selected"
                onClick={() => {}}
              >
                Reset access
              </button>
            )}
          </div>

          <h2>
            {mode === "login"
              ? "Welcome back"
              : mode === "register"
              ? "Create your account"
              : mode === "forgot"
              ? "Reset your password"
              : "Enter new password"}
          </h2>
          <p className="auth-sub">
            {mode === "login"
              ? "Sign in with your Brightloop account."
              : mode === "register"
              ? "Public sign-up creates a customer account. Staff accounts are created by an admin."
              : mode === "forgot"
              ? "Enter your account email to receive a secure password reset link."
              : "Enter the reset token received and choose your new strong password."}
          </p>

          {resetNotice && (
            <div className="banner banner-info" style={{ marginBottom: "14px", fontSize: "12px" }}>
              <CircleCheck size={16} />
              <div>{resetNotice}</div>
            </div>
          )}

          {resetError && (
            <div className="auth-error" style={{ marginBottom: "14px" }}>
              <AlertCircle size={15} /> {resetError}
            </div>
          )}

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

            {(mode === "login" || mode === "register" || mode === "forgot") && (
              <label>
                Email address
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
            )}

            {(mode === "login" || mode === "register") && (
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
            )}

            {mode === "reset" && (
              <>
                <label>
                  Reset token
                  <input
                    name="token"
                    type="text"
                    value={form.token}
                    onChange={update}
                    required
                    placeholder="Paste token from email / backend log"
                  />
                </label>
                <label>
                  New password
                  <input
                    name="newPassword"
                    type="password"
                    value={form.newPassword}
                    onChange={update}
                    required
                    placeholder="9+ chars, 1 upper, 1 lower, 1 special"
                  />
                </label>
              </>
            )}

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

            <button className="primary-button auth-submit" type="submit" disabled={busy || resetBusy}>
              {busy || resetBusy ? (
                <>
                  <RefreshCw size={15} className="spin" /> Please wait…
                </>
              ) : mode === "login" ? (
                "Sign in"
              ) : mode === "register" ? (
                "Create account"
              ) : mode === "forgot" ? (
                "Send reset instructions"
              ) : (
                "Set new password"
              )}
            </button>

            {mode === "login" && (
              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "10px" }}>
                <button
                  type="button"
                  className="text-button"
                  style={{ fontSize: "11px", color: "#159b65", background: "none", border: 0, padding: 0 }}
                  onClick={() => setMode("forgot")}
                >
                  Forgot password?
                </button>
              </div>
            )}

            {mode === "forgot" && (
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: "12px", fontSize: "11px" }}>
                <button
                  type="button"
                  className="text-button"
                  style={{ background: "none", border: 0, padding: 0 }}
                  onClick={() => setMode("login")}
                >
                  Back to Sign in
                </button>
                <button
                  type="button"
                  className="text-button"
                  style={{ background: "none", border: 0, padding: 0 }}
                  onClick={() => setMode("reset")}
                >
                  Already have a token?
                </button>
              </div>
            )}

            {mode === "reset" && (
              <div style={{ display: "flex", justifyContent: "flex-start", marginTop: "12px", fontSize: "11px" }}>
                <button
                  type="button"
                  className="text-button"
                  style={{ background: "none", border: 0, padding: 0 }}
                  onClick={() => setMode("login")}
                >
                  Back to Sign in
                </button>
              </div>
            )}
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

// ---------------------------------------------------------------- catalog modals
function CreatePlanModal({ onClose, onCreated, notify }) {
  const [name, setName] = useState("");
  const [cycle, setCycle] = useState("monthly");
  const [price, setPrice] = useState("");
  const [minQty, setMinQty] = useState(1);
  const [availFrom, setAvailFrom] = useState("");
  const [availTo, setAvailTo] = useState("");
  const [autoClose, setAutoClose] = useState(false);
  const [allowEarlyClose, setAllowEarlyClose] = useState(true);
  const [allowPause, setAllowPause] = useState(true);
  const [allowRenew, setAllowRenew] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.createPlan({
        name,
        billing_cycle: cycle,
        price: parseFloat(price),
        min_quantity: Number(minQty),
        available_from: availFrom || null,
        available_to: availTo || null,
        auto_close: autoClose,
        allow_early_close: allowEarlyClose,
        allow_pause: allowPause,
        allow_renew: allowRenew,
      });
      if (notify) notify(`Plan "${name}" created successfully!`);
      onCreated();
    } catch (err) {
      setError(err.message || "Failed to create plan");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <form className="modal modal-wide" onSubmit={submit}>
        <div className="modal-heading">
          <div>
            <h3>Create pricing plan</h3>
            <p>Configure plan terms, recurring billing cycle, and lifecycle rules.</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose}><X size={20} /></button>
        </div>

        {error && <div className="auth-error"><AlertCircle size={15} /> {error}</div>}

        <label>
          Plan name
          <input type="text" placeholder="e.g. Enterprise Yearly" value={name} onChange={(e) => setName(e.target.value)} required />
        </label>

        <div className="form-row-2">
          <label>
            Billing cycle
            <select value={cycle} onChange={(e) => setCycle(e.target.value)}>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
              <option value="yearly">Yearly</option>
            </select>
          </label>
          <label>
            Base price (₹)
            <input type="number" step="0.01" min="0" placeholder="1180.00" value={price} onChange={(e) => setPrice(e.target.value)} required />
          </label>
        </div>

        <div className="form-row-3">
          <label>
            Minimum seats/qty
            <input type="number" min="1" value={minQty} onChange={(e) => setMinQty(e.target.value)} required />
          </label>
          <label>
            Available from (optional)
            <input type="date" value={availFrom} onChange={(e) => setAvailFrom(e.target.value)} />
          </label>
          <label>
            Available to (optional)
            <input type="date" value={availTo} onChange={(e) => setAvailTo(e.target.value)} />
          </label>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", margin: "10px 0" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "12px", cursor: "pointer" }}>
            <input type="checkbox" checked={allowPause} onChange={(e) => setAllowPause(e.target.checked)} />
            Allow customer to pause
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "12px", cursor: "pointer" }}>
            <input type="checkbox" checked={allowRenew} onChange={(e) => setAllowRenew(e.target.checked)} />
            Allow contract renewal
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "12px", cursor: "pointer" }}>
            <input type="checkbox" checked={allowEarlyClose} onChange={(e) => setAllowEarlyClose(e.target.checked)} />
            Allow early cancellation
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "12px", cursor: "pointer" }}>
            <input type="checkbox" checked={autoClose} onChange={(e) => setAutoClose(e.target.checked)} />
            Auto-close when expired
          </label>
        </div>

        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="submit" className="primary-button" disabled={busy}>
            {busy ? "Saving..." : "Create plan"}
          </button>
        </div>
      </form>
    </div>
  );
}

function CreateProductModal({ onClose, onCreated, notify }) {
  const [name, setName] = useState("");
  const [type, setType] = useState("subscription");
  const [salesPrice, setSalesPrice] = useState("");
  const [costPrice, setCostPrice] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.createProduct({
        name,
        type,
        sales_price: parseFloat(salesPrice),
        cost_price: costPrice ? parseFloat(costPrice) : 0,
        notes: notes || undefined,
      });
      if (notify) notify(`Product "${name}" added to catalog!`);
      onCreated();
    } catch (err) {
      setError(err.message || "Failed to create product");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <form className="modal" onSubmit={submit}>
        <div className="modal-heading">
          <div>
            <h3>Add new product</h3>
            <p>Publish a core subscription item or add-on product to the catalog.</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose}><X size={20} /></button>
        </div>

        {error && <div className="auth-error"><AlertCircle size={15} /> {error}</div>}

        <label>
          Product name
          <input type="text" placeholder="e.g. CloudPro, Extra Seat, Odoo Connector" value={name} onChange={(e) => setName(e.target.value)} required />
        </label>

        <label>
          Product type
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="subscription">Subscription (recurring service / software)</option>
            <option value="addon">Add-on (seats, support packs, storage modules)</option>
          </select>
        </label>

        <div className="form-row-2">
          <label>
            Sales price (₹)
            <input type="number" step="0.01" min="0" placeholder="2000.00" value={salesPrice} onChange={(e) => setSalesPrice(e.target.value)} required />
          </label>
          <label>
            Cost price (₹)
            <input type="number" step="0.01" min="0" placeholder="800.00" value={costPrice} onChange={(e) => setCostPrice(e.target.value)} />
          </label>
        </div>

        <label>
          Commercial notes
          <textarea rows="2" placeholder="Product features, delivery terms, etc." value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>

        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="submit" className="primary-button" disabled={busy}>
            {busy ? "Saving..." : "Save product"}
          </button>
        </div>
      </form>
    </div>
  );
}

function CreateVariantModal({ product, onClose, onCreated, notify }) {
  const [attribute, setAttribute] = useState("Brand");
  const [value, setValue] = useState("");
  const [priceDelta, setPriceDelta] = useState("0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.createProductVariant(product.id, {
        attribute,
        value,
        price_delta: parseFloat(priceDelta),
      });
      if (notify) notify(`Variant "${attribute}: ${value}" added to ${product.name}!`);
      onCreated();
    } catch (err) {
      setError(err.message || "Failed to add variant");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <form className="modal" onSubmit={submit}>
        <div className="modal-heading">
          <div>
            <h3>Add variant to {product.name}</h3>
            <p>Offer product options (e.g., Brand: Odoo adding ₹560 to price).</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose}><X size={20} /></button>
        </div>

        {error && <div className="auth-error"><AlertCircle size={15} /> {error}</div>}

        <label>
          Variant attribute
          <input type="text" placeholder="e.g. Brand, Edition, Tier, Region" value={attribute} onChange={(e) => setAttribute(e.target.value)} required />
        </label>

        <label>
          Attribute value
          <input type="text" placeholder="e.g. Odoo, Enterprise, US-East" value={value} onChange={(e) => setValue(e.target.value)} required />
        </label>

        <label>
          Price adjustment delta (₹)
          <input type="number" step="0.01" placeholder="e.g. 560.00 (or 0 for included)" value={priceDelta} onChange={(e) => setPriceDelta(e.target.value)} required />
        </label>

        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="submit" className="primary-button" disabled={busy}>
            {busy ? "Adding..." : "Add variant"}
          </button>
        </div>
      </form>
    </div>
  );
}

function CreateTaxModal({ products, onClose, onCreated, notify }) {
  const [name, setName] = useState("");
  const [rate, setRate] = useState("18.0");
  const [taxIncluded, setTaxIncluded] = useState(false);
  const [priority, setPriority] = useState(10);
  const [productId, setProductId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.createTax({
        name,
        rate: parseFloat(rate),
        tax_included: taxIncluded,
        priority: Number(priority),
        product_id: productId ? Number(productId) : null,
      });
      if (notify) notify(`Tax rule "${name}" created!`);
      onCreated();
    } catch (err) {
      setError(err.message || "Failed to create tax rule");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <form className="modal" onSubmit={submit}>
        <div className="modal-heading">
          <div>
            <h3>New tax rule</h3>
            <p>Rules govern automatic line-item tax calculations on every invoice.</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose}><X size={20} /></button>
        </div>

        {error && <div className="auth-error"><AlertCircle size={15} /> {error}</div>}

        <label>
          Rule name
          <input type="text" placeholder="e.g. GST 18, VAT 5%, Exemption" value={name} onChange={(e) => setName(e.target.value)} required />
        </label>

        <div className="form-row-2">
          <label>
            Tax rate (%)
            <input type="number" step="0.01" min="0" max="100" placeholder="18.0" value={rate} onChange={(e) => setRate(e.target.value)} required />
          </label>
          <label>
            Evaluation priority
            <input type="number" min="1" max="100" value={priority} onChange={(e) => setPriority(e.target.value)} required />
          </label>
        </div>

        <label>
          Applicable product (leave blank for Global)
          <select value={productId} onChange={(e) => setProductId(e.target.value)}>
            <option value="">Global (all products)</option>
            {products.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </label>

        <label style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "12px", cursor: "pointer", marginTop: "8px" }}>
          <input type="checkbox" checked={taxIncluded} onChange={(e) => setTaxIncluded(e.target.checked)} />
          <span><strong>Tax included in price</strong> (extracted from base price instead of added on top)</span>
        </label>

        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="submit" className="primary-button" disabled={busy}>
            {busy ? "Saving..." : "Save tax rule"}
          </button>
        </div>
      </form>
    </div>
  );
}

function CreateDiscountModal({ products, onClose, onCreated, notify }) {
  const [name, setName] = useState("");
  const [type, setType] = useState("percentage");
  const [value, setValue] = useState("");
  const [scope, setScope] = useState("subscription");
  const [minQty, setMinQty] = useState("");
  const [minPurchase, setMinPurchase] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [usageLimit, setUsageLimit] = useState("");
  const [productId, setProductId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.createDiscount({
        name,
        type,
        value: parseFloat(value),
        scope,
        min_quantity: minQty ? Number(minQty) : null,
        min_purchase: minPurchase ? parseFloat(minPurchase) : null,
        starts_at: startsAt || null,
        ends_at: endsAt || null,
        usage_limit: usageLimit ? Number(usageLimit) : null,
        product_id: productId ? Number(productId) : null,
      });
      if (notify) notify(`Discount code "${name}" created!`);
      onCreated();
    } catch (err) {
      setError(err.message || "Failed to create discount rule");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <form className="modal modal-wide" onSubmit={submit}>
        <div className="modal-heading">
          <div>
            <h3>Create discount rule</h3>
            <p>Rules apply automatically to eligible invoices and stop when expired or exhausted.</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose}><X size={20} /></button>
        </div>

        {error && <div className="auth-error"><AlertCircle size={15} /> {error}</div>}

        <div className="form-row-2">
          <label>
            Discount code / name
            <input type="text" placeholder="e.g. SEAT-10, EARLYBIRD" value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Discount type
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="percentage">Percentage (%) off</option>
              <option value="fixed">Fixed amount (₹) off</option>
            </select>
          </label>
        </div>

        <div className="form-row-2">
          <label>
            Discount value ({type === "percentage" ? "%" : "₹"})
            <input type="number" step="0.01" min="0" placeholder={type === "percentage" ? "10.0" : "500.00"} value={value} onChange={(e) => setValue(e.target.value)} required />
          </label>
          <label>
            Scope
            <select value={scope} onChange={(e) => setScope(e.target.value)}>
              <option value="subscription">Whole subscription</option>
              <option value="product">Specific product</option>
            </select>
          </label>
        </div>

        {scope === "product" && (
          <label>
            Target product
            <select value={productId} onChange={(e) => setProductId(e.target.value)} required>
              <option value="">Select a product...</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </label>
        )}

        <div className="form-row-2">
          <label>
            Minimum seats / quantity (optional)
            <input type="number" min="1" placeholder="e.g. 10" value={minQty} onChange={(e) => setMinQty(e.target.value)} />
          </label>
          <label>
            Minimum purchase total (optional)
            <input type="number" step="0.01" min="0" placeholder="e.g. 5000.00" value={minPurchase} onChange={(e) => setMinPurchase(e.target.value)} />
          </label>
        </div>

        <div className="form-row-3">
          <label>
            Start date
            <input type="date" value={startsAt} onChange={(e) => setStartsAt(e.target.value)} />
          </label>
          <label>
            End date
            <input type="date" value={endsAt} onChange={(e) => setEndsAt(e.target.value)} />
          </label>
          <label>
            Usage limit (times)
            <input type="number" min="1" placeholder="e.g. 100" value={usageLimit} onChange={(e) => setUsageLimit(e.target.value)} />
          </label>
        </div>

        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="submit" className="primary-button" disabled={busy}>
            {busy ? "Saving..." : "Create discount rule"}
          </button>
        </div>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------- plans & catalog hub
function PlansPage({ plans, subscriptions, isStaff, isAdmin, onCreate, notify, onRefresh }) {
  const [tab, setTab] = useState("plans"); // plans | products | taxes | discounts
  const [products, setProducts] = useState([]);
  const [taxes, setTaxes] = useState([]);
  const [discounts, setDiscounts] = useState([]);
  const [loadingExtras, setLoadingExtras] = useState(false);

  // Modals state
  const [createPlanOpen, setCreatePlanOpen] = useState(false);
  const [createProdOpen, setCreateProdOpen] = useState(false);
  const [variantProduct, setVariantProduct] = useState(null);
  const [createTaxOpen, setCreateTaxOpen] = useState(false);
  const [createDiscountOpen, setCreateDiscountOpen] = useState(false);

  async function loadExtras() {
    setLoadingExtras(true);
    try {
      const [prodRes, taxRes, discRes] = await Promise.allSettled([
        api.products(),
        api.taxes(),
        api.discounts(),
      ]);
      if (prodRes.status === "fulfilled") setProducts(prodRes.value?.items || (Array.isArray(prodRes.value) ? prodRes.value : []));
      if (taxRes.status === "fulfilled") setTaxes(Array.isArray(taxRes.value) ? taxRes.value : (taxRes.value?.items || []));
      if (discRes.status === "fulfilled") setDiscounts(Array.isArray(discRes.value) ? discRes.value : (discRes.value?.items || []));
    } catch (_) {}
    finally {
      setLoadingExtras(false);
    }
  }

  useEffect(() => {
    loadExtras();
  }, [tab]);

  async function handleTogglePlanStatus(plan) {
    try {
      if (plan.status === "active") {
        await api.closePlan(plan.id);
        if (notify) notify(`Plan "${plan.name}" closed`);
      } else {
        await api.reopenPlan(plan.id);
        if (notify) notify(`Plan "${plan.name}" reopened`);
      }
      if (onRefresh) onRefresh();
    } catch (err) {
      if (notify) notify(err.message || "Failed to update plan status", "error");
    }
  }

  async function handleDeleteVariant(variantId) {
    if (!window.confirm("Delete this product variant?")) return;
    try {
      await api.deleteVariant(variantId);
      if (notify) notify("Variant removed");
      loadExtras();
    } catch (err) {
      if (notify) notify(err.message || "Failed to remove variant", "error");
    }
  }

  return (
    <div style={{ display: "grid", gap: "20px" }}>
      {/* Subtab Navigation */}
      <div className="subtab-nav">
        <button
          className={`subtab-btn ${tab === "plans" ? "active" : ""}`}
          onClick={() => setTab("plans")}
        >
          <Layers size={16} /> Pricing Plans ({plans.length})
        </button>
        <button
          className={`subtab-btn ${tab === "products" ? "active" : ""}`}
          onClick={() => setTab("products")}
        >
          <Tag size={16} /> Products & Variants ({products.length})
        </button>
        <button
          className={`subtab-btn ${tab === "taxes" ? "active" : ""}`}
          onClick={() => setTab("taxes")}
        >
          <Receipt size={16} /> Tax Rules ({taxes.length})
        </button>
        <button
          className={`subtab-btn ${tab === "discounts" ? "active" : ""}`}
          onClick={() => setTab("discounts")}
        >
          <Percent size={16} /> Discount Rules ({discounts.length})
        </button>
      </div>

      {/* TAB 1: PLANS */}
      {tab === "plans" && (
        <section className="panel full-panel">
          <div className="panel-heading page-table-heading">
            <div>
              <h3>Subscription Plans & Pricing</h3>
              <p>Billing frequencies, availability schedules, and lifecycle policies.</p>
            </div>
            {isAdmin && (
              <button className="primary-button" onClick={() => setCreatePlanOpen(true)}>
                <Plus size={16} /> Create new plan
              </button>
            )}
          </div>

          <div className="plans-grid" style={{ padding: "16px 20px" }}>
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
                    {plan.autoClose ? "Auto-closes at expiry" : "Continues billing after expiry"}
                  </div>
                  <div className="feature-line">
                    <CircleCheck size={16} /> Early cancellation{" "}
                    {plan.allowEarlyClose ? "allowed" : "blocked"}
                  </div>
                  <p className="plan-availability">
                    {plan.availableFrom || plan.availableTo
                      ? `Available ${formatDate(plan.availableFrom)} – ${formatDate(plan.availableTo)}`
                      : "Always available"}
                  </p>

                  <div style={{ display: "flex", gap: "8px", marginTop: "14px", flexWrap: "wrap" }}>
                    {isStaff && (
                      <button
                        className="plan-action"
                        style={{ flex: 1 }}
                        onClick={() => onCreate(plan.id)}
                        disabled={!available}
                      >
                        {available ? "Create subscription" : "Plan closed"} <ArrowRight size={15} />
                      </button>
                    )}
                    {isAdmin && (
                      <button
                        className={`btn-sm ${available ? "btn-danger" : "btn-success"}`}
                        onClick={() => handleTogglePlanStatus(plan)}
                      >
                        {available ? "Close plan" : "Reopen plan"}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* TAB 2: PRODUCTS & VARIANTS */}
      {tab === "products" && (
        <section className="panel full-panel">
          <div className="panel-heading page-table-heading">
            <div>
              <h3>Products & Variants</h3>
              <p>Manage subscription items, add-on features, and pricing variant deltas (e.g. Brand: Odoo +₹560).</p>
            </div>
            {isAdmin && (
              <button className="primary-button" onClick={() => setCreateProdOpen(true)}>
                <Plus size={16} /> Add product
              </button>
            )}
          </div>

          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Product name</th>
                  <th>Type</th>
                  <th>Sales price</th>
                  <th>Cost price</th>
                  <th>Variants & modifiers</th>
                  <th>Status</th>
                  <th style={{ textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {loadingExtras ? (
                  <tr>
                    <td colSpan={7} className="table-loading">
                      <RefreshCw size={18} className="spin" /> Loading product catalog…
                    </td>
                  </tr>
                ) : products.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="empty-state">No products found.</td>
                  </tr>
                ) : (
                  products.map((p) => {
                    const variants = p.variants || [];
                    return (
                      <tr key={p.id}>
                        <td>
                          <strong>{p.name}</strong>
                          {p.notes && <div className="muted" style={{ fontSize: "10px" }}>{p.notes}</div>}
                        </td>
                        <td>
                          <span className="tag-pill">{p.type.toUpperCase()}</span>
                        </td>
                        <td><strong>{formatMoney(p.sales_price)}</strong></td>
                        <td>{p.cost_price ? formatMoney(p.cost_price) : "—"}</td>
                        <td>
                          {variants.length === 0 ? (
                            <span className="muted">No variants</span>
                          ) : (
                            <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                              {variants.map((v) => (
                                <span className="variant-chip" key={v.id}>
                                  {v.attribute}: {v.value} ({parseFloat(v.price_delta) >= 0 ? `+${formatMoney(v.price_delta)}` : formatMoney(v.price_delta)})
                                  {isAdmin && (
                                    <button className="delete-btn" title="Delete variant" onClick={() => handleDeleteVariant(v.id)}>
                                      <X size={11} />
                                    </button>
                                  )}
                                </span>
                              ))}
                            </div>
                          )}
                        </td>
                        <td>
                          <Status value={p.is_active ? "active" : "disabled"} />
                        </td>
                        <td style={{ textAlign: "right" }}>
                          {isAdmin && (
                            <button className="btn-sm secondary-button" onClick={() => setVariantProduct(p)}>
                              <Plus size={12} /> Add variant
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* TAB 3: TAX RULES */}
      {tab === "taxes" && (
        <section className="panel full-panel">
          <div className="panel-heading page-table-heading">
            <div>
              <h3>Tax Rules & Invoicing Engines</h3>
              <p>Automatic tax rates applied per line item based on global rules or product specificity.</p>
            </div>
            {isAdmin && (
              <button className="primary-button" onClick={() => setCreateTaxOpen(true)}>
                <Plus size={16} /> New tax rule
              </button>
            )}
          </div>

          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Rule name</th>
                  <th>Rate</th>
                  <th>Tax inclusion</th>
                  <th>Priority</th>
                  <th>Product scope</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {loadingExtras ? (
                  <tr>
                    <td colSpan={6} className="table-loading">
                      <RefreshCw size={18} className="spin" /> Loading tax rules…
                    </td>
                  </tr>
                ) : taxes.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="empty-state">No tax rules configured.</td>
                  </tr>
                ) : (
                  taxes.map((t) => (
                    <tr key={t.id}>
                      <td><strong>{t.name}</strong></td>
                      <td><strong>{t.rate}%</strong></td>
                      <td>
                        <span className={`tag-pill ${t.tax_included ? "badge-risk-low" : ""}`}>
                          {t.tax_included ? "Included in price" : "Added on top"}
                        </span>
                      </td>
                      <td>Priority {t.priority}</td>
                      <td>
                        {t.product_id
                          ? (products.find((p) => p.id === t.product_id)?.name || `Product #${t.product_id}`)
                          : "Global (All Products)"}
                      </td>
                      <td><Status value={t.is_active ? "active" : "disabled"} /></td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* TAB 4: DISCOUNT RULES */}
      {tab === "discounts" && (
        <section className="panel full-panel">
          <div className="panel-heading page-table-heading">
            <div>
              <h3>Discount Rules & Volume Pricing</h3>
              <p>Promotional codes, volume seat tiers, and contract discounts evaluated on billing day.</p>
            </div>
            {isAdmin && (
              <button className="primary-button" onClick={() => setCreateDiscountOpen(true)}>
                <Plus size={16} /> New discount rule
              </button>
            )}
          </div>

          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Discount code</th>
                  <th>Type & Value</th>
                  <th>Scope</th>
                  <th>Minimum condition</th>
                  <th>Validity period</th>
                  <th>Usage tracking</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {loadingExtras ? (
                  <tr>
                    <td colSpan={7} className="table-loading">
                      <RefreshCw size={18} className="spin" /> Loading discounts…
                    </td>
                  </tr>
                ) : discounts.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="empty-state">No discount rules found.</td>
                  </tr>
                ) : (
                  discounts.map((d) => (
                    <tr key={d.id}>
                      <td><strong>{d.name}</strong></td>
                      <td>
                        <strong>{d.type === "percentage" ? `${d.value}% OFF` : `₹${d.value} OFF`}</strong>
                      </td>
                      <td>
                        <span className="tag-pill">{d.scope.toUpperCase()}</span>
                      </td>
                      <td>
                        {d.min_quantity ? `≥ ${d.min_quantity} seats` : ""}
                        {d.min_purchase ? ` (min ₹${d.min_purchase})` : ""}
                        {!d.min_quantity && !d.min_purchase && "No minimum"}
                      </td>
                      <td>
                        {d.starts_at || d.ends_at
                          ? `${d.starts_at ? formatDate(d.starts_at) : "Any"} – ${d.ends_at ? formatDate(d.ends_at) : "Forever"}`
                          : "Always valid"}
                      </td>
                      <td>
                        <span className="tag-pill" style={{ background: d.usage_limit && d.used_count >= d.usage_limit ? "#fee2e2" : "#e0eee5" }}>
                          {d.used_count || 0} {d.usage_limit ? `/ ${d.usage_limit}` : "uses"}
                        </span>
                      </td>
                      <td><Status value={d.is_active ? "active" : "disabled"} /></td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Modals */}
      {createPlanOpen && (
        <CreatePlanModal
          onClose={() => setCreatePlanOpen(false)}
          onCreated={() => { setCreatePlanOpen(false); if (onRefresh) onRefresh(); }}
          notify={notify}
        />
      )}

      {createProdOpen && (
        <CreateProductModal
          onClose={() => setCreateProdOpen(false)}
          onCreated={() => { setCreateProdOpen(false); loadExtras(); if (onRefresh) onRefresh(); }}
          notify={notify}
        />
      )}

      {variantProduct && (
        <CreateVariantModal
          product={variantProduct}
          onClose={() => setVariantProduct(null)}
          onCreated={() => { setVariantProduct(null); loadExtras(); }}
          notify={notify}
        />
      )}

      {createTaxOpen && (
        <CreateTaxModal
          products={products}
          onClose={() => setCreateTaxOpen(false)}
          onCreated={() => { setCreateTaxOpen(false); loadExtras(); }}
          notify={notify}
        />
      )}

      {createDiscountOpen && (
        <CreateDiscountModal
          products={products}
          onClose={() => setCreateDiscountOpen(false)}
          onCreated={() => { setCreateDiscountOpen(false); loadExtras(); }}
          notify={notify}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------- customers
function CreateCustomerModal({ onClose, onCreated, notify }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.createCustomer({ name, email, password });
      if (notify) notify(`Customer account for ${name} created!`);
      onCreated();
    } catch (err) {
      setError(err.message || "Failed to create customer");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <form className="modal" onSubmit={submit}>
        <div className="modal-heading">
          <div>
            <h3>Add customer account</h3>
            <p>Create a customer profile and credentials for portal access.</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose}><X size={20} /></button>
        </div>

        {error && <div className="auth-error"><AlertCircle size={15} /> {error}</div>}

        <label>
          Company / customer name
          <input type="text" placeholder="e.g. Acme Technologies Ltd" value={name} onChange={(e) => setName(e.target.value)} required />
        </label>

        <label>
          Email address
          <input type="email" placeholder="owner@acme.io" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>

        <label>
          Temporary password
          <input type="password" placeholder="Must meet complexity rules" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>

        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="submit" className="primary-button" disabled={busy}>
            {busy ? "Creating..." : "Create customer"}
          </button>
        </div>
      </form>
    </div>
  );
}

function CustomersPage({ customers, subscriptions, isAdmin, onRefresh, notify }) {
  const [createOpen, setCreateOpen] = useState(false);

  async function handleToggleStatus(customer) {
    try {
      await api.updateCustomer(customer.id, { is_active: !customer.active });
      if (notify) notify(`Customer ${customer.name} ${customer.active ? "disabled" : "activated"}`);
      if (onRefresh) onRefresh();
    } catch (err) {
      if (notify) notify(err.message || "Failed to update customer status", "error");
    }
  }

  if (!customers.length) {
    return (
      <section className="panel full-panel">
        <div className="panel-heading">
          <div>
            <h3>Customers</h3>
            <p>Customer accounts are created through registration or the admin API.</p>
          </div>
          {isAdmin && (
            <button className="primary-button" onClick={() => setCreateOpen(true)}>
              <Plus size={16} /> Add customer
            </button>
          )}
        </div>
        <p className="empty-state">No customer accounts returned by the backend yet.</p>
        {createOpen && (
          <CreateCustomerModal
            onClose={() => setCreateOpen(false)}
            onCreated={() => { setCreateOpen(false); if (onRefresh) onRefresh(); }}
            notify={notify}
          />
        )}
      </section>
    );
  }

  return (
    <section className="panel full-panel">
      <div className="panel-heading page-table-heading">
        <div>
          <h3>Customers & Accounts</h3>
          <p>Directory of customer accounts and their active subscriptions.</p>
        </div>
        {isAdmin && (
          <button className="primary-button" onClick={() => setCreateOpen(true)}>
            <Plus size={16} /> Add customer
          </button>
        )}
      </div>

      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Customer</th>
              <th>Active subscriptions</th>
              <th>Plans</th>
              <th>Joined</th>
              <th>Status</th>
              {isAdmin && <th style={{ textAlign: "right" }}>Actions</th>}
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
                  <td><strong>{activeSubs.length}</strong></td>
                  <td>{plans.length ? plans.join(", ") : "—"}</td>
                  <td>{formatDate(customer.joined)}</td>
                  <td>
                    <Status value={customer.active ? "active" : "disabled"} />
                  </td>
                  {isAdmin && (
                    <td style={{ textAlign: "right" }}>
                      <button
                        className={`btn-sm ${customer.active ? "btn-danger" : "btn-success"}`}
                        onClick={() => handleToggleStatus(customer)}
                      >
                        {customer.active ? "Deactivate" : "Activate"}
                      </button>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {createOpen && (
        <CreateCustomerModal
          onClose={() => setCreateOpen(false)}
          onCreated={() => { setCreateOpen(false); if (onRefresh) onRefresh(); }}
          notify={notify}
        />
      )}
    </section>
  );
}

// ---------------------------------------------------------------- quotations
function CreateQuotationModal({ customers, plans, products, onClose, onCreated }) {
  const [customerId, setCustomerId] = useState(customers[0]?.id || "");
  const [planId, setPlanId] = useState(plans[0]?.id || "");
  const [productId, setProductId] = useState(products[0]?.id || "");
  const [quantity, setQuantity] = useState(1);
  const [validityDays, setValidityDays] = useState(30);
  const [notes, setNotes] = useState("");
  const [templates, setTemplates] = useState([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.quoteTemplates().then((res) => {
      if (Array.isArray(res)) setTemplates(res);
    }).catch(() => {});
  }, []);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = {
        customer_id: Number(customerId),
        plan_id: planId ? Number(planId) : undefined,
        template_id: selectedTemplateId ? Number(selectedTemplateId) : undefined,
        validity_days: Number(validityDays),
        notes: notes || undefined,
        lines: [
          {
            product_id: Number(productId),
            quantity: Number(quantity),
          },
        ],
      };
      await api.createQuotation(payload);
      onCreated();
    } catch (err) {
      setError(err.message || "Failed to create quotation");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <form className="modal" onSubmit={submit}>
        <div className="modal-heading">
          <div>
            <h3>New quotation</h3>
            <p>Draft a formal proposal for a customer.</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        {templates.length > 0 && (
          <label>
            Template (optional)
            <select
              value={selectedTemplateId}
              onChange={(e) => {
                const val = e.target.value;
                setSelectedTemplateId(val);
                const t = templates.find((item) => item.id === Number(val));
                if (t?.plan_id) setPlanId(t.plan_id);
              }}
            >
              <option value="">Start from scratch</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
        )}

        <label>
          Customer
          <select value={customerId} onChange={(e) => setCustomerId(e.target.value)} required>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.email})
              </option>
            ))}
          </select>
        </label>

        <label>
          Plan
          <select value={planId} onChange={(e) => setPlanId(e.target.value)}>
            <option value="">No specific plan</option>
            {plans.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({formatMoney(p.price)}/{p.cycle})
              </option>
            ))}
          </select>
        </label>

        <div className="form-row">
          <label>
            Primary product
            <select value={productId} onChange={(e) => setProductId(e.target.value)} required>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Quantity
            <input
              type="number"
              min="1"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              required
            />
          </label>
        </div>

        <label>
          Validity (days)
          <input
            type="number"
            min="1"
            max="365"
            value={validityDays}
            onChange={(e) => setValidityDays(e.target.value)}
          />
        </label>

        <label>
          Proposal notes / terms
          <textarea
            rows="2"
            value={notes}
            placeholder="Special commercial terms, payment notes, etc."
            onChange={(e) => setNotes(e.target.value)}
          />
        </label>

        {error && (
          <div className="auth-error">
            <AlertCircle size={15} /> {error}
          </div>
        )}

        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="primary-button" disabled={busy}>
            {busy ? "Drafting..." : "Create quotation"}
          </button>
        </div>
      </form>
    </div>
  );
}

function QuotationsPage({ user, isStaff, plans, customers, products, notify, onSelectSub }) {
  const [quotations, setQuotations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("all");
  const [actionId, setActionId] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);

  async function loadQuotations() {
    setLoading(true);
    setError(null);
    try {
      let q = "";
      if (filter !== "all") q = `status=${filter}`;
      const res = await api.quotations(q);
      setQuotations(res?.items || (Array.isArray(res) ? res : []));
    } catch (err) {
      setError(err.message || "Failed to load quotations");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadQuotations();
  }, [filter]);

  async function handleSend(id) {
    setActionId(id);
    try {
      await api.sendQuotation(id);
      if (notify) notify("Quotation sent to customer");
      loadQuotations();
    } catch (err) {
      if (notify) notify(err.message || "Failed to send quotation", "error");
    } finally {
      setActionId(null);
    }
  }

  async function handleConfirm(id) {
    setActionId(id);
    try {
      const res = await api.confirmQuotation(id);
      if (notify) notify("Quotation accepted & subscription created!");
      loadQuotations();
      if (res?.subscription && onSelectSub) {
        onSelectSub(res.subscription);
      }
    } catch (err) {
      if (notify) notify(err.message || "Failed to confirm quotation", "error");
    } finally {
      setActionId(null);
    }
  }

  async function handleCancel(id) {
    if (!window.confirm("Cancel this quotation?")) return;
    setActionId(id);
    try {
      await api.cancelQuotation(id);
      if (notify) notify("Quotation cancelled");
      loadQuotations();
    } catch (err) {
      if (notify) notify(err.message || "Failed to cancel quotation", "error");
    } finally {
      setActionId(null);
    }
  }

  async function handleDownload(q) {
    setActionId(`pdf-${q.id}`);
    try {
      await api.downloadQuotationPdf(q.id, `${q.number || `QUO-${q.id}`}.pdf`);
    } catch (err) {
      if (notify) notify(err.message || "Failed to download quotation PDF", "error");
    } finally {
      setActionId(null);
    }
  }

  return (
    <section className="panel full-panel">
      <div className="panel-heading page-table-heading">
        <div>
          <h3>{isStaff ? "Quotations & proposals" : "My quotations"}</h3>
          <p>{isStaff ? "Draft, publish, and convert quotations into active subscriptions." : "Review and accept quotations sent by the sales team."}</p>
        </div>
        {isStaff && (
          <button className="primary-button" onClick={() => setCreateOpen(true)}>
            <Plus size={16} /> New quotation
          </button>
        )}
      </div>

      <div className="filter-row">
        {["all", "draft", "sent", "confirmed", "cancelled"].map((tab) => (
          <button
            key={tab}
            className={filter === tab ? "filter-tab selected" : "filter-tab"}
            onClick={() => setFilter(tab)}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {error && (
        <div className="banner banner-error">
          <AlertCircle size={16} />
          <div>{error}</div>
          <button onClick={loadQuotations}>Retry</button>
        </div>
      )}

      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Quotation #</th>
              <th>Customer</th>
              <th>Plan</th>
              <th>Valid until</th>
              <th>Total amount</th>
              <th>Status</th>
              <th style={{ textAlign: "right" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="table-loading">
                  <RefreshCw size={18} className="spin" /> Loading quotations…
                </td>
              </tr>
            ) : quotations.length === 0 ? (
              <tr>
                <td colSpan={7} className="empty-state">
                  No quotations found.
                </td>
              </tr>
            ) : (
              quotations.map((q) => {
                const customerName = q.customer_name || (customers.find(c => c.id === q.customer_id)?.name) || `Customer #${q.customer_id}`;
                const planName = q.plan_name || (plans.find(p => p.id === q.plan_id)?.name) || "Custom plan";
                return (
                  <tr key={q.id}>
                    <td>
                      <strong>{q.number}</strong>
                    </td>
                    <td>{customerName}</td>
                    <td>{planName}</td>
                    <td>{q.valid_until ? formatDate(q.valid_until) : "—"}</td>
                    <td>
                      <strong>{formatMoney(q.total || 0)}</strong>
                    </td>
                    <td>
                      <Status value={q.status} />
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <div className="table-actions">
                        <button
                          className="icon-button"
                          onClick={() => handleDownload(q)}
                          disabled={actionId === `pdf-${q.id}`}
                          title="Download PDF Quotation"
                        >
                          <Download size={15} />
                        </button>

                        {/* Customer Accept */}
                        {!isStaff && q.status === "sent" && (
                          <button
                            className="btn-sm btn-success"
                            onClick={() => handleConfirm(q.id)}
                            disabled={actionId === q.id}
                            title="Accept this quotation"
                          >
                            <Check size={12} /> Accept quotation
                          </button>
                        )}

                        {/* Staff actions */}
                        {isStaff && q.status === "draft" && (
                          <>
                            <button
                              className="btn-sm secondary-button"
                              onClick={() => handleSend(q.id)}
                              disabled={actionId === q.id}
                              title="Send quotation to customer"
                            >
                              <Send size={12} /> Send
                            </button>
                            <button
                              className="btn-sm btn-success"
                              onClick={() => handleConfirm(q.id)}
                              disabled={actionId === q.id}
                              title="Confirm directly into subscription"
                            >
                              <Check size={12} /> Confirm
                            </button>
                            <button
                              className="btn-sm btn-danger"
                              onClick={() => handleCancel(q.id)}
                              disabled={actionId === q.id}
                              title="Cancel quotation"
                            >
                              <X size={12} />
                            </button>
                          </>
                        )}

                        {isStaff && q.status === "sent" && (
                          <>
                            <button
                              className="btn-sm btn-success"
                              onClick={() => handleConfirm(q.id)}
                              disabled={actionId === q.id}
                              title="Confirm quotation"
                            >
                              <Check size={12} /> Confirm
                            </button>
                            <button
                              className="btn-sm btn-danger"
                              onClick={() => handleCancel(q.id)}
                              disabled={actionId === q.id}
                              title="Cancel quotation"
                            >
                              <X size={12} />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {createOpen && (
        <CreateQuotationModal
          customers={customers}
          plans={plans}
          products={products}
          onClose={() => setCreateOpen(false)}
          onCreated={() => {
            setCreateOpen(false);
            loadQuotations();
            if (notify) notify("Quotation drafted successfully!");
          }}
        />
      )}
    </section>
  );
}

// ---------------------------------------------------------------- record payment modal
function RecordPaymentModal({ invoice, onClose, onSuccess, notify }) {
  const [amount, setAmount] = useState(invoice.outstanding || invoice.total || "");
  const [method, setMethod] = useState("bank_transfer");
  const [paidAt, setPaidAt] = useState(new Date().toISOString().slice(0, 10));
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    const numAmount = parseFloat(amount);
    if (!numAmount || numAmount <= 0) {
      setError("Please enter a valid positive payment amount");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.recordPayment({
        invoice_id: invoice.id,
        amount: numAmount,
        method,
        paid_at: paidAt,
        note: note || undefined,
      });
      notify(`Payment of ${formatMoney(numAmount)} recorded for ${invoice.number}`);
      onSuccess();
    } catch (err) {
      setError(err.message || "Failed to record payment");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-heading">
          <div>
            <h3>Record Payment</h3>
            <p>Invoice {invoice.number} · Outstanding: {formatMoney(invoice.outstanding || invoice.total)}</p>
          </div>
          <button className="icon-button" onClick={onClose}><X size={18} /></button>
        </div>

        {error && <div className="banner banner-error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-grid">
            <label>
              Amount (INR)
              <input
                type="number"
                step="0.01"
                min="0.01"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                required
              />
            </label>
            <label>
              Payment Method
              <select value={method} onChange={(e) => setMethod(e.target.value)}>
                <option value="bank_transfer">Bank Transfer</option>
                <option value="card">Credit / Debit Card</option>
                <option value="upi">UPI</option>
                <option value="cash">Cash</option>
                <option value="cheque">Cheque</option>
                <option value="other">Other</option>
              </select>
            </label>
          </div>

          <label>
            Payment Date
            <input
              type="date"
              value={paidAt}
              onChange={(e) => setPaidAt(e.target.value)}
              required
            />
          </label>

          <label>
            Reference Note (optional)
            <input
              type="text"
              placeholder="e.g. Bank ref #TRX-987654"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>

          <div className="modal-actions">
            <button type="button" className="secondary-button" onClick={onClose} disabled={submitting}>
              Cancel
            </button>
            <button type="submit" className="primary-button" disabled={submitting}>
              {submitting ? "Recording..." : "Confirm Payment"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- invoices
function InvoicesPage({ user, isStaff, notify }) {
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("all");
  const [actionId, setActionId] = useState(null);
  const [paymentModalInvoice, setPaymentModalInvoice] = useState(null);
  const [billingRunning, setBillingRunning] = useState(false);
  const [billingNotice, setBillingNotice] = useState(null);

  async function loadInvoices() {
    setLoading(true);
    setError(null);
    try {
      let q = "";
      if (filter === "overdue") q = "overdue=true";
      else if (filter !== "all") q = `status=${filter}`;
      const res = await api.invoices(q);
      setInvoices(res?.items || (Array.isArray(res) ? res : []));
    } catch (err) {
      setError(err.message || "Failed to load invoices");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadInvoices();
  }, [filter]);

  async function handleConfirm(id) {
    setActionId(id);
    try {
      await api.confirmInvoice(id);
      if (notify) notify("Invoice confirmed successfully");
      loadInvoices();
    } catch (err) {
      if (notify) notify(err.message || "Failed to confirm invoice", "error");
    } finally {
      setActionId(null);
    }
  }

  async function handleCancel(id) {
    if (!window.confirm("Are you sure you want to cancel this draft invoice?")) return;
    setActionId(id);
    try {
      await api.cancelInvoice(id);
      if (notify) notify("Invoice cancelled");
      loadInvoices();
    } catch (err) {
      if (notify) notify(err.message || "Failed to cancel invoice", "error");
    } finally {
      setActionId(null);
    }
  }

  async function handleSend(id) {
    setActionId(id);
    try {
      await api.sendInvoice(id);
      if (notify) notify("Invoice sent to customer");
      loadInvoices();
    } catch (err) {
      if (notify) notify(err.message || "Failed to send invoice", "error");
    } finally {
      setActionId(null);
    }
  }

  async function handleDownload(inv) {
    setActionId(`pdf-${inv.id}`);
    try {
      await api.downloadInvoicePdf(inv.id, inv.number);
      if (notify) notify(`Downloaded PDF for ${inv.number}`);
    } catch (err) {
      if (notify) notify(err.message || "PDF download failed", "error");
    } finally {
      setActionId(null);
    }
  }

  async function handleRunBilling(mode) {
    setBillingRunning(true);
    setBillingNotice(null);
    try {
      const today = new Date().toISOString().slice(0, 10);
      const res = await api.runBilling({ mode, run_date: today });
      setBillingNotice(res);
      if (notify) {
        notify(
          mode === "dry_run"
            ? `Dry Run: ${res.created_count} eligible subscriptions evaluated (0 written)`
            : `Live Run: ${res.created_count} invoices generated successfully!`
        );
      }
      loadInvoices();
    } catch (err) {
      if (notify) notify(err.message || "Billing run failed", "error");
    } finally {
      setBillingRunning(false);
    }
  }

  return (
    <section className="panel full-panel">
      <div className="panel-heading page-table-heading">
        <div>
          <h3>Invoices & Billing Operations</h3>
          <p>
            {isStaff
              ? "Live recurring invoices, payment reconciliation, and billing engine execution."
              : "Review your invoices, download official PDFs, and track payment receipts."}
          </p>
        </div>
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
          {isStaff && (
            <>
              <button
                className="secondary-button"
                onClick={() => handleRunBilling("dry_run")}
                disabled={billingRunning}
                title="Simulate billing without creating real invoices or modifying state"
              >
                <Play size={14} /> {billingRunning ? "Running..." : "Simulate Dry Run"}
              </button>
              <button
                className="primary-button"
                onClick={() => handleRunBilling("live")}
                disabled={billingRunning}
                title="Bill all subscriptions currently due"
              >
                <Zap size={14} /> {billingRunning ? "Running..." : "Execute Billing Run"}
              </button>
            </>
          )}
          <button className="secondary-button" onClick={loadInvoices} disabled={loading}>
            <RefreshCw size={14} className={loading ? "spin" : ""} /> Refresh
          </button>
        </div>
      </div>

      {billingNotice && (
        <div className="panel-body-padded">
          <div className={`banner ${billingNotice.mode === "dry_run" ? "banner-warning" : "banner-info"}`}>
            <Info size={16} />
            <div>
              <strong>
                Billing {billingNotice.mode === "dry_run" ? "Dry Run (Simulation)" : "Live Run"} Completed
              </strong>
              <span>
                {" "}— Run #{billingNotice.id || billingNotice.run_id}: {billingNotice.created_count} subscriptions processed,{" "}
                {billingNotice.success_count || 0} succeeded, {billingNotice.skipped_count || 0} skipped,{" "}
                {billingNotice.failed_count || 0} failed.
              </span>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="panel-body-padded">
          <div className="banner banner-error">{error}</div>
        </div>
      )}

      {/* Filter Tabs */}
      <div className="filter-row">
        {[
          { id: "all", label: "All Invoices" },
          { id: "confirmed", label: "Confirmed" },
          { id: "paid", label: "Paid" },
          { id: "draft", label: "Draft" },
          { id: "overdue", label: "Overdue" },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setFilter(t.id)}
            className={filter === t.id ? "filter-tab selected" : "filter-tab"}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Invoice #</th>
              <th>Customer</th>
              <th>Issue Date</th>
              <th>Due Date</th>
              <th>Total</th>
              <th>Outstanding</th>
              <th>Status</th>
              <th>Payment State</th>
              <th style={{ textAlign: "right" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={9} style={{ textAlign: "center", padding: "30px", color: "#8a9790" }}>
                  <RefreshCw size={18} className="spin" style={{ margin: "auto", display: "block" }} />
                  Loading invoices from backend...
                </td>
              </tr>
            ) : invoices.length === 0 ? (
              <tr>
                <td colSpan={9} style={{ textAlign: "center", padding: "35px", color: "#8a9790" }}>
                  No invoices found matching this filter.
                  {isStaff && " Click 'Execute Billing Run' above to bill active subscriptions."}
                </td>
              </tr>
            ) : (
              invoices.map((inv) => {
                const isOverdue = inv.is_overdue || inv._is_overdue;
                const outstanding = inv.outstanding !== undefined ? inv.outstanding : inv.total;
                return (
                  <tr key={inv.id}>
                    <td>
                      <strong>{inv.number}</strong>
                    </td>
                    <td>Customer #{inv.customer_id}</td>
                    <td>{formatDate(inv.issue_date)}</td>
                    <td>
                      {formatDate(inv.due_date)}
                      {isOverdue && (
                        <span className="badge-overdue" style={{ marginLeft: "6px" }}>
                          Overdue ({inv.days_overdue || 1}d)
                        </span>
                      )}
                    </td>
                    <td>
                      <strong>{formatMoney(inv.total)}</strong>
                    </td>
                    <td style={{ color: parseFloat(outstanding) > 0 ? "#b8564c" : "#15945f" }}>
                      {formatMoney(outstanding)}
                    </td>
                    <td>
                      <Status value={inv.status} />
                    </td>
                    <td>
                      <span className={`tag-pill ${inv.payment_state === "paid" ? "badge-risk-low" : ""}`}>
                        {(inv.payment_state || "unpaid").toUpperCase()}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <div className="table-actions">
                        <button
                          className="icon-button"
                          onClick={() => handleDownload(inv)}
                          disabled={actionId === `pdf-${inv.id}`}
                          title="Download PDF Invoice"
                        >
                          <Download size={15} />
                        </button>

                        {isStaff && inv.status === "draft" && (
                          <>
                            <button
                              className="btn-sm btn-success"
                              onClick={() => handleConfirm(inv.id)}
                              disabled={actionId === inv.id}
                              title="Confirm draft invoice"
                            >
                              <Check size={12} /> Confirm
                            </button>
                            <button
                              className="btn-sm btn-danger"
                              onClick={() => handleCancel(inv.id)}
                              disabled={actionId === inv.id}
                              title="Cancel draft invoice"
                            >
                              <X size={12} />
                            </button>
                          </>
                        )}

                        {isStaff && inv.status === "confirmed" && (
                          <button
                            className="btn-sm secondary-button"
                            onClick={() => handleSend(inv.id)}
                            disabled={actionId === inv.id}
                            title="Send invoice email link"
                          >
                            <Send size={12} /> Send
                          </button>
                        )}

                        {isStaff && inv.status === "confirmed" && parseFloat(outstanding) > 0 && (
                          <button
                            className="btn-sm btn-success"
                            onClick={() => setPaymentModalInvoice(inv)}
                            title="Record payment for this invoice"
                          >
                            <DollarSign size={12} /> Pay
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {paymentModalInvoice && (
        <RecordPaymentModal
          invoice={paymentModalInvoice}
          onClose={() => setPaymentModalInvoice(null)}
          onSuccess={() => {
            setPaymentModalInvoice(null);
            loadInvoices();
          }}
          notify={notify}
        />
      )}
    </section>
  );
}

// ---------------------------------------------------------------- analytics
function AnalyticsPage({ subscriptions, isStaff, notify }) {
  const [summary, setSummary] = useState(null);
  const [mrrData, setMrrData] = useState(null);
  const [overdue, setOverdue] = useState([]);
  const [risk, setRisk] = useState([]);
  const [forecast, setForecast] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  async function loadAnalytics() {
    setLoading(true);
    setError(null);
    try {
      const [sumRes, mrrRes, ovRes, riskRes, fcRes] = await Promise.allSettled([
        api.reportsSummary(),
        api.reportsMrr(),
        api.reportsOverdue(),
        api.insightsRisk(),
        api.insightsForecast(4),
      ]);
      if (sumRes.status === "fulfilled") setSummary(sumRes.value);
      if (mrrRes.status === "fulfilled") setMrrData(mrrRes.value);
      if (ovRes.status === "fulfilled") setOverdue(ovRes.value?.items || []);
      if (riskRes.status === "fulfilled") setRisk(riskRes.value?.items || []);
      if (fcRes.status === "fulfilled") setForecast(fcRes.value);
    } catch (err) {
      setError(err.message || "Failed to load reports and insights");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAnalytics();
  }, []);

  const liveMrr = summary?.mrr ? parseFloat(summary.mrr) : 0;
  const liveArr = summary?.arr ? parseFloat(summary.arr) : liveMrr * 12;
  const overdueTotal = summary?.overdue_total ? parseFloat(summary.overdue_total) : 0;
  const unsettledTotal = summary?.unsettled_total ? parseFloat(summary.unsettled_total) : 0;
  const highRiskCount = risk.filter((r) => r.risk_level === "high").length;

  return (
    <div style={{ display: "grid", gap: "22px" }}>
      {/* Top Real-time Financial KPIs */}
      <div className="metrics-grid">
        <MetricCard
          title="Monthly Recurring Revenue"
          value={formatMoney(liveMrr)}
          change="Live /reports/summary"
          positive
          icon={CreditCard}
          note="Normalized ex-tax MRR"
        />
        <MetricCard
          title="Annualized Run Rate (ARR)"
          value={formatMoney(liveArr)}
          change="MRR × 12"
          positive
          icon={TrendingUp}
          note="Projected annual revenue"
        />
        <MetricCard
          title="Unsettled Invoices"
          value={formatMoney(unsettledTotal)}
          change={`${summary?.unsettled_invoices_count || 0} pending`}
          positive={unsettledTotal === 0}
          icon={Receipt}
          note="Confirmed & partial balances"
        />
        <MetricCard
          title="Overdue Receivables"
          value={formatMoney(overdueTotal)}
          change={`${summary?.overdue_invoices_count || 0} overdue`}
          positive={overdueTotal === 0}
          icon={AlertCircle}
          note="Requires collections action"
        />
      </div>

      {/* Row 2: MRR Forecast & Revenue Guardian Risk Scoring */}
      <div className="bottom-grid" style={{ display: "grid", gridTemplateColumns: "1.1fr 1fr", gap: "20px" }}>
        {/* MRR Trend & Forecast */}
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h3>MRR Growth & Holt-Linear Projections</h3>
              <p>Historical monthly MRR combined with statistical trend projection</p>
            </div>
            <span className="tag-pill" style={{ background: "#eaf6ee", color: "#168752" }}>
              {forecast?.method ? `Method: ${forecast.method.toUpperCase()}` : "Holt-Linear Engine"}
            </span>
          </div>

          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Period</th>
                  <th>MRR</th>
                  <th>Growth</th>
                  <th>Type</th>
                </tr>
              </thead>
              <tbody>
                {mrrData?.series && mrrData.series.length > 0 ? (
                  mrrData.series.map((s) => (
                    <tr key={s.period}>
                      <td><strong>{s.period}</strong></td>
                      <td>{formatMoney(s.mrr)}</td>
                      <td style={{ color: s.growth_pct >= 0 ? "#15945f" : "#c45c52" }}>
                        {s.growth_pct !== null ? `${s.growth_pct > 0 ? "+" : ""}${s.growth_pct}%` : "—"}
                      </td>
                      <td><span className="tag-pill">Historical</span></td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td><strong>{new Date().toISOString().slice(0, 7)}</strong></td>
                    <td>{formatMoney(liveMrr)}</td>
                    <td style={{ color: "#15945f" }}>+0.0%</td>
                    <td><span className="tag-pill">Current</span></td>
                  </tr>
                )}

                {/* Forecasted points */}
                {forecast?.points &&
                  forecast.points.map((pt) => (
                    <tr key={pt.period} style={{ background: "#fbfcfb" }}>
                      <td><strong>{pt.period}</strong></td>
                      <td style={{ color: "#128653" }}><strong>{formatMoney(pt.mrr)}</strong></td>
                      <td style={{ color: pt.growth_pct >= 0 ? "#15945f" : "#c45c52" }}>
                        {pt.growth_pct !== null ? `${pt.growth_pct > 0 ? "+" : ""}${pt.growth_pct}%` : "—"}
                      </td>
                      <td><span className="tag-pill badge-risk-low">Projected</span></td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Revenue Guardian: Churn Risk Scoring */}
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h3>Revenue Guardian — Risk Intelligence</h3>
              <p>Automated subscription churn & payment delinquency scoring</p>
            </div>
            {highRiskCount > 0 && (
              <span className="badge-risk-high">{highRiskCount} High Risk</span>
            )}
          </div>

          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Subscription</th>
                  <th>Customer</th>
                  <th>Risk Level</th>
                  <th>Key Factors</th>
                </tr>
              </thead>
              <tbody>
                {risk.length === 0 ? (
                  <tr>
                    <td colSpan={4} style={{ textAlign: "center", padding: "28px", color: "#8a9790" }}>
                      No subscription risk anomalies detected.
                    </td>
                  </tr>
                ) : (
                  risk.map((r) => {
                    const levelClass =
                      r.risk_level === "high"
                        ? "badge-risk-high"
                        : r.risk_level === "medium"
                        ? "badge-risk-medium"
                        : "badge-risk-low";
                    return (
                      <tr key={r.subscription_id}>
                        <td><strong>#{r.subscription_id}</strong></td>
                        <td>Customer #{r.customer_id}</td>
                        <td>
                          <span className={levelClass}>
                            {r.risk_level.toUpperCase()} ({r.risk_score})
                          </span>
                        </td>
                        <td>
                          {r.reasons && r.reasons.length > 0 ? (
                            r.reasons.map((reason, i) => (
                              <span key={i} className="tag-pill" style={{ marginRight: "4px" }}>
                                {reason}
                              </span>
                            ))
                          ) : (
                            <span style={{ color: "#8a9790", fontSize: "10px" }}>Healthy</span>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      {/* Row 3: Overdue Chase List */}
      <section className="panel full-panel">
        <div className="panel-heading">
          <div>
            <h3>Overdue Invoices Chase List</h3>
            <p>Prioritized collections queue for accounts with past-due payment dates</p>
          </div>
          <button className="secondary-button" onClick={loadAnalytics}>
            <RefreshCw size={13} className={loading ? "spin" : ""} /> Refresh List
          </button>
        </div>

        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Invoice #</th>
                <th>Customer</th>
                <th>Due Date</th>
                <th>Days Overdue</th>
                <th>Total</th>
                <th>Outstanding</th>
                <th style={{ textAlign: "right" }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {overdue.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: "center", padding: "30px", color: "#168653" }}>
                    <CircleCheck size={20} style={{ display: "block", margin: "0 auto 8px" }} />
                    No overdue invoices! All issued accounts are current and settled.
                  </td>
                </tr>
              ) : (
                overdue.map((item) => (
                  <tr key={item.id}>
                    <td><strong>{item.number}</strong></td>
                    <td>{item.customer_name || `Customer #${item.customer_id}`}</td>
                    <td>{formatDate(item.due_date)}</td>
                    <td>
                      <span className="badge-overdue">{item.days_overdue} days</span>
                    </td>
                    <td>{formatMoney(item.total)}</td>
                    <td style={{ color: "#b8564c", fontWeight: "700" }}>
                      {formatMoney(item.outstanding)}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <button
                        className="btn-sm secondary-button"
                        onClick={() => api.downloadInvoicePdf(item.id, item.number)}
                      >
                        <Download size={13} /> PDF
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}


// ---------------------------------------------------------------- settings
function SettingsPage({ user, roleLabel, lastSynced, loading, onRefresh, onLogout, notify }) {
  const [currPassword, setCurrPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [pwdBusy, setPwdBusy] = useState(false);
  const [pwdMsg, setPwdMsg] = useState({ text: "", error: false });

  // Admin staff management
  const [staff, setStaff] = useState([]);
  const [staffLoading, setStaffLoading] = useState(false);
  const [newStaffName, setNewStaffName] = useState("");
  const [newStaffEmail, setNewStaffEmail] = useState("");
  const [newStaffPassword, setNewStaffPassword] = useState("");
  const [addStaffOpen, setAddStaffOpen] = useState(false);
  const [staffBusy, setStaffBusy] = useState(false);

  const isAdmin = user.role === "admin";

  useEffect(() => {
    if (isAdmin) {
      loadStaff();
    }
  }, [isAdmin]);

  async function loadStaff() {
    setStaffLoading(true);
    try {
      const res = await api.staffList();
      setStaff(res?.items || (Array.isArray(res) ? res : []));
    } catch (_) {}
    finally {
      setStaffLoading(false);
    }
  }

  async function handlePasswordChange(e) {
    e.preventDefault();
    setPwdBusy(true);
    setPwdMsg({ text: "", error: false });
    try {
      await api.changePassword({ current_password: currPassword, new_password: newPassword });
      setPwdMsg({ text: "Password updated successfully!", error: false });
      setCurrPassword("");
      setNewPassword("");
      if (notify) notify("Password updated successfully!");
    } catch (err) {
      setPwdMsg({ text: err.message || "Failed to update password", error: true });
    } finally {
      setPwdBusy(false);
    }
  }

  async function handleToggleStaff(s) {
    try {
      await api.updateStaff(s.id, { is_active: !s.is_active });
      loadStaff();
      if (notify) notify(`Staff ${s.name} ${!s.is_active ? "activated" : "deactivated"}`);
    } catch (err) {
      if (notify) notify(err.message || "Failed to update staff status", "error");
    }
  }

  async function handleCreateStaff(e) {
    e.preventDefault();
    setStaffBusy(true);
    try {
      await api.createStaff({ name: newStaffName, email: newStaffEmail, password: newStaffPassword });
      setAddStaffOpen(false);
      setNewStaffName("");
      setNewStaffEmail("");
      setNewStaffPassword("");
      loadStaff();
      if (notify) notify("Staff member added successfully!");
    } catch (err) {
      if (notify) notify(err.message || "Failed to add staff member", "error");
    } finally {
      setStaffBusy(false);
    }
  }

  return (
    <div style={{ display: "grid", gap: "22px" }}>
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

      {/* Security & Password */}
      <section className="panel settings-panel">
        <h3>Security & credentials</h3>
        <p>Update your account access password.</p>

        {pwdMsg.text && (
          <div className={`banner ${pwdMsg.error ? "banner-error" : "banner-info"}`}>
            {pwdMsg.error ? <AlertCircle size={16} /> : <CircleCheck size={16} />}
            <div>{pwdMsg.text}</div>
          </div>
        )}

        <form onSubmit={handlePasswordChange} style={{ display: "grid", gap: "12px", maxWidth: "420px", marginTop: "12px" }}>
          <label>
            Current password
            <input
              type="password"
              value={currPassword}
              onChange={(e) => setCurrPassword(e.target.value)}
              required
            />
          </label>
          <label>
            New password
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="9+ chars, 1 upper, 1 lower, 1 special"
              required
            />
          </label>
          <button type="submit" className="primary-button" disabled={pwdBusy} style={{ justifySelf: "start" }}>
            {pwdBusy ? "Updating..." : "Update password"}
          </button>
        </form>
      </section>

      {/* Admin: Staff Team Management */}
      {isAdmin && (
        <section className="panel full-panel">
          <div className="panel-heading">
            <div>
              <h3>Staff team management</h3>
              <p>Configure staff credentials and active roles (Admin only).</p>
            </div>
            <button className="primary-button" onClick={() => setAddStaffOpen(true)}>
              <Plus size={16} /> Add staff member
            </button>
          </div>

          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Staff name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th style={{ textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {staffLoading ? (
                  <tr>
                    <td colSpan={5} className="table-loading">
                      <RefreshCw size={18} className="spin" /> Loading team…
                    </td>
                  </tr>
                ) : staff.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="empty-state">No staff members found.</td>
                  </tr>
                ) : (
                  staff.map((s) => (
                    <tr key={s.id}>
                      <td><strong>{s.name}</strong></td>
                      <td>{s.email}</td>
                      <td><span className="tag-pill">{s.role.toUpperCase()}</span></td>
                      <td>
                        <Status value={s.is_active ? "active" : "disabled"} />
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <button
                          className={`btn-sm ${s.is_active ? "btn-danger" : "btn-success"}`}
                          onClick={() => handleToggleStaff(s)}
                        >
                          {s.is_active ? "Deactivate" : "Activate"}
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {addStaffOpen && (
            <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) setAddStaffOpen(false); }}>
              <form className="modal" onSubmit={handleCreateStaff}>
                <div className="modal-heading">
                  <div>
                    <h3>Add staff member</h3>
                    <p>Grant operations and billing access to a team member.</p>
                  </div>
                  <button type="button" className="icon-button" onClick={() => setAddStaffOpen(false)}>
                    <X size={20} />
                  </button>
                </div>

                <label>
                  Full name
                  <input
                    type="text"
                    value={newStaffName}
                    onChange={(e) => setNewStaffName(e.target.value)}
                    required
                  />
                </label>

                <label>
                  Email address
                  <input
                    type="email"
                    value={newStaffEmail}
                    onChange={(e) => setNewStaffEmail(e.target.value)}
                    required
                  />
                </label>

                <label>
                  Temporary password
                  <input
                    type="password"
                    placeholder="Must meet password requirements"
                    value={newStaffPassword}
                    onChange={(e) => setNewStaffPassword(e.target.value)}
                    required
                  />
                </label>

                <div className="modal-actions">
                  <button type="button" className="secondary-button" onClick={() => setAddStaffOpen(false)} disabled={staffBusy}>
                    Cancel
                  </button>
                  <button type="submit" className="primary-button" disabled={staffBusy}>
                    {staffBusy ? "Creating..." : "Create staff account"}
                  </button>
                </div>
              </form>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- modals
const TODAY_ISO = new Date().toISOString().slice(0, 10);

function AddSubscriptionModal({ customers, plans, products, initialPlanId, onClose, onCreated }) {
  const availablePlans = plans.filter((plan) => plan.status === "active");
  const startingPlan =
    availablePlans.find((plan) => plan.id === Number(initialPlanId)) || availablePlans[0] || null;

  const [customerSearch, setCustomerSearch] = useState("");
  const filteredCustomers = useMemo(() => {
    if (!customerSearch.trim()) return customers;
    const term = customerSearch.trim().toLowerCase();
    return customers.filter((c) =>
      `${c.name || ""} ${c.email || ""}`.toLowerCase().includes(term)
    );
  }, [customers, customerSearch]);

  const [customerId, setCustomerId] = useState(
    filteredCustomers[0]?.id || customers[0]?.id || ""
  );
  const [planId, setPlanId] = useState(startingPlan?.id || "");
  const [productId, setProductId] = useState(products[0]?.id || "");
  const [quantity, setQuantity] = useState(startingPlan?.minQuantity || 1);
  const [startDate, setStartDate] = useState(TODAY_ISO);
  const [paymentTerms, setPaymentTerms] = useState("Net 30");
  const [autoActivate, setAutoActivate] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (filteredCustomers.length > 0 && !filteredCustomers.some((c) => c.id === Number(customerId))) {
      setCustomerId(filteredCustomers[0].id);
    }
  }, [filteredCustomers]);

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
      const created = await api.createSubscription({
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
      if (autoActivate && created?.id) {
        try {
          await api.sendSubscription(created.id);
          await api.confirmSubscription(created.id);
          await api.activateSubscription(created.id);
        } catch (e) {
          console.warn("Could not auto-activate:", e);
        }
      }
      const customer = customers.find((item) => item.id === Number(customerId));
      onCreated(`Subscription created${autoActivate ? " & activated" : ""} for ${customer?.name || "customer"}`);
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
          <input
            type="text"
            placeholder="Type to filter customer name or email..."
            value={customerSearch}
            onChange={(e) => setCustomerSearch(e.target.value)}
            style={{ marginBottom: "6px" }}
          />
          <select
            value={customerId}
            onChange={(event) => setCustomerId(event.target.value)}
            required
          >
            {filteredCustomers.length === 0 ? (
              <option value="" disabled>No customer found matching "{customerSearch}"</option>
            ) : (
              filteredCustomers.map((customer) => (
                <option key={customer.id} value={customer.id}>
                  {customer.name} · {customer.email}
                </option>
              ))
            )}
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

        <label style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "13px", cursor: "pointer", marginTop: "12px", userSelect: "none" }}>
          <input
            type="checkbox"
            checked={autoActivate}
            onChange={(e) => setAutoActivate(e.target.checked)}
          />
          <span><strong>Activate immediately</strong> (draft &rarr; quotation &rarr; confirmed &rarr; active)</span>
        </label>

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

function SubscriptionDetailModal({
  subscription,
  user,
  isStaff,
  onClose,
  onUpdated,
  notify,
}) {
  const [sub, setSub] = useState(subscription);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");

  const runAction = async (fn, successMsg) => {
    try {
      setBusy(true);
      setActionError("");
      const res = await fn();
      if (res && res.id) {
        setSub(normalizeSubscription(res));
      } else {
        try {
          const fresh = await api.getSubscription(sub.id);
          if (fresh) setSub(normalizeSubscription(fresh));
        } catch (_) {}
      }
      if (notify) notify(successMsg);
      if (onUpdated) await onUpdated();
    } catch (err) {
      setActionError(err.message || "Failed to update subscription.");
    } finally {
      setBusy(false);
    }
  };

  const handleSend = () => {
    runAction(() => api.sendSubscription(sub.id), `Quotation sent for ${sub.number}`);
  };

  const handleConfirm = () => {
    runAction(() => api.confirmSubscription(sub.id), `Subscription ${sub.number} confirmed!`);
  };

  const handleActivate = () => {
    runAction(() => api.activateSubscription(sub.id), `Subscription ${sub.number} activated!`);
  };

  const handleQuickActivate = () => {
    runAction(async () => {
      if (sub.status === "draft") {
        await api.sendSubscription(sub.id);
      }
      if (sub.status === "draft" || sub.status === "quotation") {
        await api.confirmSubscription(sub.id);
      }
      return await api.activateSubscription(sub.id);
    }, `Subscription ${sub.number} is now active!`);
  };

  const handlePause = () => {
    const reason = window.prompt("Reason for pause (optional):", "Customer requested pause");
    if (reason === null) return;
    runAction(() => api.pauseSubscription(sub.id, reason), `Subscription ${sub.number} paused.`);
  };

  const handleResume = () => {
    runAction(() => api.resumeSubscription(sub.id), `Subscription ${sub.number} resumed!`);
  };

  const handleClose = () => {
    const reason = window.prompt("Reason for cancellation (optional):", "Customer requested cancellation");
    if (reason === null) return;
    runAction(() => api.closeSubscription(sub.id, reason), `Subscription ${sub.number} cancelled.`);
  };

  const handleRevise = () => {
    runAction(() => api.reviseSubscription(sub.id), `Subscription ${sub.number} revised to draft.`);
  };

  const handleRenew = () => {
    const ext = window.prompt("New expiry date (YYYY-MM-DD) or leave blank to extend one cycle:", "");
    if (ext === null) return;
    runAction(
      () => api.renewSubscription(sub.id, ext.trim() ? { new_expiry_date: ext.trim() } : {}),
      `Subscription ${sub.number} renewed!`
    );
  };

  const handleBillNow = () => {
    runAction(async () => {
      await api.billSubscriptionNow(sub.id);
      return await api.getSubscription(sub.id);
    }, `Invoice generated for ${sub.number}!`);
  };

  return (
    <div
      className="modal-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <div className="modal detail-modal" style={{ maxWidth: "680px" }}>
        <div className="modal-heading">
          <div>
            <h3>{sub.number}</h3>
            <p>
              {sub.customer} · {sub.plan}
            </p>
          </div>
          <button className="icon-button" onClick={onClose} disabled={busy}>
            <X size={20} />
          </button>
        </div>

        <div className="detail-status" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "16px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <Status value={sub.status} />
            <span className="muted">{sub.paymentTerms || "No payment terms"}</span>
          </div>
          {sub.raw?.quotation_id && (
            <button
              type="button"
              className="btn-sm secondary-button"
              style={{ display: "inline-flex", alignItems: "center", gap: "5px" }}
              onClick={() => api.downloadQuotationPdf(sub.raw.quotation_id, `${sub.number}-quote.pdf`)}
            >
              <Download size={13} /> Download Quotation PDF
            </button>
          )}
        </div>

        {actionError && (
          <div className="auth-error" style={{ marginBottom: "16px" }}>
            <AlertCircle size={15} /> {actionError}
          </div>
        )}

        {/* Role & status guidance */}
        {sub.status === "draft" && !isStaff && (
          <div style={{ background: "#f0f9ff", border: "1px solid #bae6fd", padding: "10px 14px", borderRadius: "8px", color: "#0369a1", fontSize: "12px", marginBottom: "16px", display: "flex", alignItems: "center", gap: "8px" }}>
            <Info size={16} />
            <span>This subscription is currently in draft review by the operations team. Once published as a quotation, you can approve it here.</span>
          </div>
        )}

        {sub.status === "quotation" && (
          <div style={{ background: "#ecfdf5", border: "1px solid #a7f3d0", padding: "10px 14px", borderRadius: "8px", color: "#065f46", fontSize: "12px", marginBottom: "16px", display: "flex", alignItems: "center", gap: "8px" }}>
            <Sparkles size={16} />
            <span>Quotation ready for review! Click <strong>Accept & Confirm</strong> below to approve this subscription.</span>
          </div>
        )}

        {sub.status === "confirmed" && !isStaff && (
          <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", padding: "10px 14px", borderRadius: "8px", color: "#15803d", fontSize: "12px", marginBottom: "16px", display: "flex", alignItems: "center", gap: "8px" }}>
            <Check size={16} />
            <span>Subscription confirmed! Our operations team is provisioning your service now.</span>
          </div>
        )}

        {sub.status === "paused" && (
          <div style={{ background: "#fffbeb", border: "1px solid #fde68a", padding: "10px 14px", borderRadius: "8px", color: "#92400e", fontSize: "12px", marginBottom: "16px", display: "flex", alignItems: "center", gap: "8px" }}>
            <Clock size={16} />
            <span>This subscription is currently paused {sub.raw?.pause_reason ? `(${sub.raw.pause_reason})` : ""}. No billing will occur while paused. Click <strong>Resume</strong> below to reactivate.</span>
          </div>
        )}

        {sub.status === "closed" && (
          <div style={{ background: "#f3f4f6", border: "1px solid #e5e7eb", padding: "10px 14px", borderRadius: "8px", color: "#6b7280", fontSize: "12px", marginBottom: "16px", display: "flex", alignItems: "center", gap: "8px" }}>
            <AlertCircle size={16} />
            <span>This subscription was cancelled {sub.raw?.close_reason ? `(${sub.raw.close_reason})` : ""}.</span>
          </div>
        )}

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

        <div className="modal-actions" style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: "8px", flexWrap: "wrap", marginTop: "20px" }}>
          <button className="secondary-button" onClick={onClose} disabled={busy}>
            Close
          </button>

          {/* Draft actions */}
          {sub.status === "draft" && isStaff && (
            <>
              <button className="secondary-button" onClick={handleSend} disabled={busy}>
                <Send size={14} /> Send Quotation
              </button>
              <button className="primary-button btn-success" onClick={handleQuickActivate} disabled={busy}>
                <Zap size={14} /> {busy ? "Activating..." : "One-Click Activate"}
              </button>
            </>
          )}

          {/* Quotation actions */}
          {sub.status === "quotation" && (
            <>
              {isStaff && (
                <>
                  <button className="secondary-button" onClick={handleRevise} disabled={busy}>
                    <RefreshCw size={14} /> Revise to Draft
                  </button>
                  <button className="secondary-button" onClick={handleQuickActivate} disabled={busy}>
                    <Zap size={14} /> {busy ? "Activating..." : "Activate Direct"}
                  </button>
                </>
              )}
              <button className="primary-button btn-success" onClick={handleConfirm} disabled={busy}>
                <Check size={14} /> {busy ? "Confirming..." : "Accept & Confirm Quotation"}
              </button>
            </>
          )}

          {/* Confirmed actions */}
          {sub.status === "confirmed" && isStaff && (
            <button className="primary-button btn-success" onClick={handleActivate} disabled={busy}>
              <Play size={14} /> {busy ? "Activating..." : "Activate Subscription"}
            </button>
          )}

          {/* Active actions */}
          {sub.status === "active" && (
            <>
              <button className="secondary-button" onClick={handlePause} disabled={busy}>
                <Pause size={14} /> Pause
              </button>
              <button className="secondary-button" onClick={handleRenew} disabled={busy}>
                <Repeat size={14} /> Renew Contract
              </button>
              <button className="btn-danger" style={{ padding: "8px 14px", borderRadius: "8px", fontWeight: "600", cursor: "pointer" }} onClick={handleClose} disabled={busy}>
                Cancel Subscription
              </button>
              {isStaff && (
                <button className="primary-button" onClick={handleBillNow} disabled={busy}>
                  <DollarSign size={14} /> {busy ? "Billing..." : "Bill Now"}
                </button>
              )}
            </>
          )}

          {/* Paused actions */}
          {sub.status === "paused" && (
            <>
              <button className="primary-button btn-success" onClick={handleResume} disabled={busy}>
                <Play size={14} /> {busy ? "Resuming..." : "Resume Subscription"}
              </button>
              <button className="btn-danger" style={{ padding: "8px 14px", borderRadius: "8px", fontWeight: "600", cursor: "pointer" }} onClick={handleClose} disabled={busy}>
                Cancel Subscription
              </button>
            </>
          )}

          {/* Closed actions */}
          {sub.status === "closed" && (
            <button className="primary-button btn-success" onClick={handleRenew} disabled={busy}>
              <Repeat size={14} /> Renew / Reopen Subscription
            </button>
          )}
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
    if (user) refreshData(user);
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
        {
          id: "quotations",
          label: isStaff ? "Quotations" : "My quotations",
          icon: FileText,
        },
        {
          id: "invoices",
          label: isStaff ? "Invoices & Billing" : "My Invoices",
          icon: Receipt,
        },
        ...(isStaff
          ? [
              { id: "plans", label: "Plans & Pricing", icon: Layers },
              { id: "customers", label: "Customers", icon: Users },
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
    quotations: isStaff ? "Quotations" : "My quotations",
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
              isAdmin={user?.role === "admin"}
              onCreate={openCreate}
              notify={notify}
              onRefresh={() => refreshData(user)}
            />
          )}
          {page === "customers" && (
            <CustomersPage
              customers={data.customers}
              subscriptions={data.subscriptions}
              isAdmin={user?.role === "admin"}
              notify={notify}
              onRefresh={() => refreshData(user)}
            />
          )}
          {page === "quotations" && (
            <QuotationsPage
              user={user}
              isStaff={isStaff}
              plans={data.plans}
              customers={data.customers}
              products={data.products}
              notify={notify}
              onSelectSub={(sub) => {
                setSelected(normalizeSubscription(sub));
                setPage("subscriptions");
              }}
            />
          )}
          {page === "invoices" && (
            <InvoicesPage user={user} isStaff={isStaff} notify={notify} />
          )}
          {page === "analytics" && (
            <AnalyticsPage
              subscriptions={data.subscriptions}
              isStaff={isStaff}
              notify={notify}
            />
          )}
          {page === "settings" && (
            <SettingsPage
              user={user}
              roleLabel={roleLabel}
              lastSynced={lastSynced}
              loading={loadingData}
              onRefresh={() => refreshData(user)}
              onLogout={handleLogout}
              notify={notify}
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
        <SubscriptionDetailModal
          subscription={selected}
          user={user}
          isStaff={isStaff}
          onClose={() => setSelected(null)}
          onUpdated={async () => {
            await refreshData(user);
          }}
          notify={notify}
        />
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
