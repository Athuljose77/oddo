
import { useState, useEffect } from "react";
import {
  LayoutDashboard, Layers, Repeat, Users, Receipt,
  ChartNoAxesCombined, Settings, Search, Bell, Plus,
  ArrowUpRight, ArrowDownRight, MoreHorizontal,
  CalendarDays, CreditCard, CircleCheck, Clock,
  AlertCircle, X, ChevronDown, Menu, Sparkles,
  Download, Filter, ArrowRight, Zap
} from "lucide-react";
import "./App.css";

const initialSubscriptions = [
  { id: "SUB-001", customer: "Olivia Rhye", email: "olivia@example.com", plan: "Pro Plan", amount: 49, cycle: "Monthly", status: "Active", date: "Nov 12, 2026" },
  { id: "SUB-002", customer: "Phoenix Baker", email: "phoenix@example.com", plan: "Enterprise", amount: 199, cycle: "Monthly", status: "Active", date: "Nov 15, 2026" },
  { id: "SUB-003", customer: "Lana Steiner", email: "lana@example.com", plan: "Starter", amount: 19, cycle: "Monthly", status: "Pending", date: "Nov 18, 2026" },
  { id: "SUB-004", customer: "Demi Wilkinson", email: "demi@example.com", plan: "Pro Plan", amount: 49, cycle: "Monthly", status: "Cancelled", date: "Nov 20, 2026" },
  { id: "SUB-005", customer: "Candice Wu", email: "candice@example.com", plan: "Enterprise", amount: 199, cycle: "Yearly", status: "Active", date: "Nov 22, 2026" },
  { id: "SUB-006", customer: "Natali Craig", email: "natali@example.com", plan: "Starter", amount: 19, cycle: "Monthly", status: "Active", date: "Nov 25, 2026" },
];

const plans = [
  { name: "Starter", price: 19, description: "For individuals getting started", features: ["Basic analytics", "Email support", "1 team member"], color: "starter", count: 124 },
  { name: "Pro Plan", price: 49, description: "For growing businesses", features: ["Advanced analytics", "Priority support", "10 team members"], color: "pro", count: 86 },
  { name: "Enterprise", price: 199, description: "For established organizations", features: ["Custom analytics", "Dedicated support", "Unlimited members"], color: "enterprise", count: 32 },
];

const customers = [
  { name: "Olivia Rhye", email: "olivia@example.com", company: "Olivia Studio", joined: "Oct 12, 2026", plan: "Pro Plan" },
  { name: "Phoenix Baker", email: "phoenix@example.com", company: "Baker Co.", joined: "Oct 15, 2026", plan: "Enterprise" },
  { name: "Lana Steiner", email: "lana@example.com", company: "Lana Designs", joined: "Oct 18, 2026", plan: "Starter" },
  { name: "Demi Wilkinson", email: "demi@example.com", company: "Demi Creative", joined: "Oct 20, 2026", plan: "Pro Plan" },
  { name: "Candice Wu", email: "candice@example.com", company: "Wu Industries", joined: "Oct 22, 2026", plan: "Enterprise" },
];

const invoices = [
  { id: "INV-2026-001", customer: "Olivia Rhye", date: "Oct 12, 2026", amount: "$49.00", status: "Paid" },
  { id: "INV-2026-002", customer: "Phoenix Baker", date: "Oct 15, 2026", amount: "$199.00", status: "Paid" },
  { id: "INV-2026-003", customer: "Lana Steiner", date: "Oct 18, 2026", amount: "$19.00", status: "Pending" },
  { id: "INV-2026-004", customer: "Demi Wilkinson", date: "Oct 20, 2026", amount: "$49.00", status: "Overdue" },
];

const navGroups = [
  {
    title: "WORKSPACE",
    items: [
      { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
      { id: "subscriptions", label: "Subscriptions", icon: Repeat },
      { id: "plans", label: "Plans & Pricing", icon: Layers },
      { id: "customers", label: "Customers", icon: Users },
      { id: "invoices", label: "Invoices & Billing", icon: Receipt },
    ],
  },
  {
    title: "INSIGHTS",
    items: [
      { id: "analytics", label: "Analytics", icon: ChartNoAxesCombined },
    ],
  },
];

function Status({ value }) {
  const type = value.toLowerCase();
  const Icon = type === "active" || type === "paid"
    ? CircleCheck
    : type === "pending"
      ? Clock
      : AlertCircle;

  return (
    <span className={`status status-${type}`}>
      <Icon size={13} />
      {value}
    </span>
  );
}

function Avatar({ name, index = 0 }) {
  const colors = ["#E5F4EB", "#E9EDFF", "#FCEBDD", "#F9E6F0", "#E5F1F7"];
  return (
    <span className="avatar" style={{ background: colors[index % colors.length] }}>
      {name.split(" ").map(part => part[0]).join("").slice(0, 2)}
    </span>
  );
}

function MetricCard({ title, value, change, positive, icon: Icon, note }) {
  return (
    <div className="metric-card">
      <div className="metric-top">
        <span>{title}</span>
        <span className="metric-icon"><Icon size={19} /></span>
      </div>
      <h2>{value}</h2>
      <div className="metric-bottom">
        <span className={positive ? "trend positive" : "trend negative"}>
          {positive ? <ArrowUpRight size={15} /> : <ArrowDownRight size={15} />}
          {change}
        </span>
        <span className="muted">{note}</span>
      </div>
    </div>
  );
}

function Dashboard({ subscriptions, setPage }) {
  const active = subscriptions.filter(s => s.status === "Active").length;
  const totalRevenue = subscriptions
    .filter(s => s.status === "Active")
    .reduce((sum, s) => sum + s.amount, 0);

  return (
    <>
      <div className="welcome-row">
        <div>
          <h2>Welcome back, Afra <span>✦</span></h2>
          <p>Here's what's happening with your subscriptions today.</p>
        </div>
        <button className="secondary-button" onClick={() => setPage("analytics")}>
          <CalendarDays size={16} /> Last 30 days <ChevronDown size={15} />
        </button>
      </div>

      <div className="metrics-grid">
        <MetricCard title="Total Revenue" value={`$${totalRevenue.toLocaleString()}`} change="+12.8%" positive icon={CreditCard} note="vs. last month" />
        <MetricCard title="Active Subscriptions" value={active.toString()} change="+8.2%" positive icon={Repeat} note="vs. last month" />
        <MetricCard title="Total Customers" value="1,284" change="+10.5%" positive icon={Users} note="vs. last month" />
        <MetricCard title="Churn Rate" value="2.4%" change="-0.6%" positive icon={ChartNoAxesCombined} note="vs. last month" />
      </div>

      <div className="dashboard-grid">
        <section className="panel revenue-panel">
          <div className="panel-heading">
            <div>
              <h3>Revenue Overview</h3>
              <p>Monthly recurring revenue</p>
            </div>
            <button className="select-button">This year <ChevronDown size={14} /></button>
          </div>
          <div className="revenue-summary">
            <strong>$24,680</strong>
            <span className="trend positive"><ArrowUpRight size={15} /> 12.8%</span>
          </div>
          <div className="chart">
            {[35, 48, 42, 60, 52, 68, 58, 76, 66, 84, 73, 95].map((height, i) => (
              <div className="chart-column" key={i}>
                <div className="chart-bar" style={{ height: `${height}%` }} />
                <span>{["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][i]}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="panel plan-panel">
          <div className="panel-heading">
            <div><h3>Subscription Plans</h3><p>Distribution by plan</p></div>
            <button className="icon-button" onClick={() => setPage("plans")}><MoreHorizontal size={19} /></button>
          </div>
          <div className="donut-wrap">
            <div className="donut"><div className="donut-center"><strong>242</strong><span>Total</span></div></div>
          </div>
          <div className="legend">
            <div><span className="dot green-dot" /> Starter <strong>124</strong></div>
            <div><span className="dot blue-dot" /> Pro Plan <strong>86</strong></div>
            <div><span className="dot orange-dot" /> Enterprise <strong>32</strong></div>
          </div>
        </section>
      </div>

      <section className="panel table-panel">
        <div className="panel-heading">
          <div><h3>Recent Subscriptions</h3><p>Keep track of your latest subscriptions</p></div>
          <button className="text-button" onClick={() => setPage("subscriptions")}>View all <ArrowRight size={15} /></button>
        </div>
        <SubscriptionTable subscriptions={subscriptions.slice(0, 5)} />
      </section>

      <div className="bottom-grid">
        <section className="panel activity-panel">
          <div className="panel-heading"><div><h3>Recent Activity</h3><p>Latest updates from your workspace</p></div></div>
          {[
            ["Olivia Rhye", "subscribed to Pro Plan", "10 minutes ago"],
            ["Phoenix Baker", "upgraded to Enterprise", "1 hour ago"],
            ["Lana Steiner", "created a new account", "3 hours ago"],
          ].map((item, i) => (
            <div className="activity-item" key={i}>
              <Avatar name={item[0]} index={i} />
              <div><strong>{item[0]}</strong><p>{item[1]}</p></div>
              <span>{item[2]}</span>
            </div>
          ))}
        </section>
        <section className="upgrade-card">
          <span className="upgrade-icon"><Sparkles size={21} /></span>
          <h3>Everything in one place.</h3>
          <p>Manage subscriptions, billing and customers with a single, simple workspace.</p>
          <button onClick={() => setPage("analytics")}>Explore analytics <ArrowRight size={15} /></button>
        </section>
      </div>
    </>
  );
}

function SubscriptionTable({ subscriptions }) {
  if (!subscriptions.length) return <p className="empty-state">No subscriptions found.</p>;

  return (
    <div className="table-scroll">
      <table>
        <thead><tr><th>Customer</th><th>Plan</th><th>Amount</th><th>Next billing</th><th>Status</th><th></th></tr></thead>
        <tbody>
          {subscriptions.map((s, i) => (
            <tr key={s.id}>
              <td><div className="customer-cell"><Avatar name={s.customer} index={i} /><div><strong>{s.customer}</strong><span>{s.email}</span></div></div></td>
              <td>{s.plan}</td>
              <td><strong>${s.amount}.00</strong><span className="table-muted">/{s.cycle.toLowerCase()}</span></td>
              <td>{s.date}</td>
              <td><Status value={s.status} /></td>
              <td><button className="icon-button"><MoreHorizontal size={18} /></button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SubscriptionsPage({ subscriptions, setSubscriptions, openModal }) {
  const [filter, setFilter] = useState("All");
  const filtered = subscriptions.filter(s => filter === "All" || s.status === filter);

  return (
    <section className="panel full-panel">
      <div className="panel-heading page-table-heading">
        <div><h3>All Subscriptions</h3><p>Manage and monitor your recurring subscriptions.</p></div>
        <button className="primary-button" onClick={openModal}><Plus size={17} /> Add subscription</button>
      </div>
      <div className="filter-row">
        {["All", "Active", "Pending", "Cancelled"].map(f => (
          <button key={f} className={filter === f ? "filter-tab selected" : "filter-tab"} onClick={() => setFilter(f)}>{f}</button>
        ))}
        <span className="filter-count">{filtered.length} subscriptions</span>
      </div>
      <SubscriptionTable subscriptions={filtered} />
    </section>
  );
}

function PlansPage({ openModal }) {
  return (
    <div className="plans-grid">
      {plans.map(plan => (
        <div className={`plan-card ${plan.color}`} key={plan.name}>
          <div className="plan-card-top"><span className="plan-symbol"><Zap size={19} /></span><span className="plan-count">{plan.count} subscribers</span></div>
          <h3>{plan.name}</h3>
          <p>{plan.description}</p>
          <div className="plan-price"><strong>${plan.price}</strong><span>/ month</span></div>
          <div className="plan-divider" />
          <h4>What's included</h4>
          {plan.features.map(feature => <div className="feature-line" key={feature}><CircleCheck size={16} /> {feature}</div>)}
          <button className="plan-action" onClick={openModal}>Create subscription <ArrowRight size={15} /></button>
        </div>
      ))}
    </div>
  );
}

function CustomersPage() {
  return (
    <section className="panel full-panel">
      <div className="panel-heading"><div><h3>Customers</h3><p>Manage your customer relationships.</p></div></div>
      <div className="table-scroll">
        <table>
          <thead><tr><th>Customer</th><th>Company</th><th>Plan</th><th>Joined</th><th>Action</th></tr></thead>
          <tbody>{customers.map((c, i) => (
            <tr key={c.email}>
              <td><div className="customer-cell"><Avatar name={c.name} index={i} /><div><strong>{c.name}</strong><span>{c.email}</span></div></div></td>
              <td>{c.company}</td><td>{c.plan}</td><td>{c.joined}</td>
              <td><button className="icon-button"><MoreHorizontal size={18} /></button></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </section>
  );
}

function InvoicesPage() {
  return (
    <section className="panel full-panel">
      <div className="panel-heading"><div><h3>Invoices & Billing</h3><p>View payment history and invoice statuses.</p></div><button className="secondary-button"><Download size={15} /> Export</button></div>
      <div className="table-scroll">
        <table>
          <thead><tr><th>Invoice</th><th>Customer</th><th>Date</th><th>Amount</th><th>Status</th><th>Download</th></tr></thead>
          <tbody>{invoices.map(inv => (
            <tr key={inv.id}><td><strong>{inv.id}</strong></td><td>{inv.customer}</td><td>{inv.date}</td><td><strong>{inv.amount}</strong></td><td><Status value={inv.status} /></td><td><button className="icon-button"><Download size={17} /></button></td></tr>
          ))}</tbody>
        </table>
      </div>
    </section>
  );
}

function AnalyticsPage() {
  return (
    <div className="analytics-grid">
      <MetricCard title="Monthly recurring revenue" value="$24,680" change="+12.8%" positive icon={CreditCard} note="compared to last month" />
      <MetricCard title="Annual recurring revenue" value="$296,160" change="+14.2%" positive icon={ChartNoAxesCombined} note="compared to last year" />
      <MetricCard title="Customer lifetime value" value="$840" change="+5.4%" positive icon={Users} note="compared to last month" />
      <MetricCard title="Churn rate" value="2.4%" change="-0.6%" positive icon={Repeat} note="compared to last month" />
      <section className="panel analytics-chart">
        <div className="panel-heading"><div><h3>Revenue performance</h3><p>Revenue growth across the year</p></div></div>
        <div className="chart large-chart">
          {[35, 48, 42, 60, 52, 68, 58, 76, 66, 84, 73, 95].map((height, i) => (
            <div className="chart-column" key={i}><div className="chart-bar" style={{ height: `${height}%` }} /><span>{["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][i]}</span></div>
          ))}
        </div>
      </section>
    </div>
  );
}

function SettingsPage() {
  return (
    <section className="panel settings-panel">
      <h3>Workspace Settings</h3>
      <p>Manage your workspace preferences.</p>
      <div className="settings-row"><div><strong>Workspace name</strong><span>Your organization name</span></div><input defaultValue="Odoo Subscriptions" /></div>
      <div className="settings-row"><div><strong>Default currency</strong><span>Currency for displaying prices</span></div><select defaultValue="USD"><option>USD</option><option>INR</option><option>EUR</option></select></div>
      <div className="settings-row"><div><strong>Billing notifications</strong><span>Receive updates about recurring payments</span></div><input type="checkbox" defaultChecked /></div>
      <button className="primary-button">Save changes</button>
    </section>
  );
}

function AddSubscriptionModal({ close, add }) {
  const [form, setForm] = useState({ customer: "", email: "", plan: "Starter", amount: "19" });
  const update = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  function submit(e) {
    e.preventDefault();
    if (!form.customer.trim() || !form.email.trim()) return;
    add({
      id: `SUB-${String(Date.now()).slice(-5)}`,
      customer: form.customer,
      email: form.email,
      plan: form.plan,
      amount: Number(form.amount),
      cycle: "Monthly",
      status: "Active",
      date: "Nov 30, 2026"
    });
    close();
  }

  return (
    <div className="modal-overlay" onMouseDown={e => { if (e.target === e.currentTarget) close(); }}>
      <form className="modal" onSubmit={submit}>
        <div className="modal-heading"><div><h3>New subscription</h3><p>Add a customer to a subscription plan.</p></div><button type="button" className="icon-button" onClick={close}><X size={20} /></button></div>
        <label>Customer name<input name="customer" value={form.customer} onChange={update} placeholder="e.g. Olivia Rhye" required /></label>
        <label>Email address<input name="email" type="email" value={form.email} onChange={update} placeholder="name@example.com" required /></label>
        <label>Subscription plan<select name="plan" value={form.plan} onChange={e => setForm({ ...form, plan: e.target.value, amount: e.target.value === "Starter" ? "19" : e.target.value === "Pro Plan" ? "49" : "199" })}><option>Starter</option><option>Pro Plan</option><option>Enterprise</option></select></label>
        <label>Monthly amount<input name="amount" type="number" min="1" value={form.amount} onChange={update} required /></label>
        <div className="modal-actions"><button type="button" className="secondary-button" onClick={close}>Cancel</button><button className="primary-button" type="submit"><Plus size={16} /> Create subscription</button></div>
      </form>
    </div>
  );
}

export default function App() {
  // Fetch backend health on mount
  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((data) => console.log('Backend health:', data))
      .catch((e) => console.error('Health fetch error:', e));
  }, []);
  const [page, setPage] = useState("dashboard");
  const [subscriptions, setSubscriptions] = useState(initialSubscriptions);
  const [search, setSearch] = useState("");
  const [modal, setModal] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const pageTitles = {
    dashboard: "Dashboard", subscriptions: "Subscriptions", plans: "Plans & Pricing",
    customers: "Customers", invoices: "Invoices & Billing", analytics: "Analytics", settings: "Settings"
  };

  const visibleSubscriptions = subscriptions.filter(s =>
    `${s.customer} ${s.email} ${s.plan} ${s.id}`.toLowerCase().includes(search.toLowerCase())
  );

  function navigate(id) {
    setPage(id);
    setMobileOpen(false);
  }

  return (
    <div className="app-shell">
      {mobileOpen && <div className="mobile-backdrop" onClick={() => setMobileOpen(false)} />}
      <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
        <div className="brand">
          <div className="brand-icon"><Layers size={21} /></div>
          <span>subscribely<span className="brand-dot">.</span></span>
          <button className="mobile-close icon-button" onClick={() => setMobileOpen(false)}><X size={20} /></button>
        </div>
        <div className="workspace-switch"><div className="workspace-avatar">O</div><div><strong>Odoo Workspace</strong><span>Free workspace</span></div><ChevronDown size={16} /></div>
        <nav>
          {navGroups.map(group => (
            <div className="nav-group" key={group.title}>
              <span className="nav-heading">{group.title}</span>
              {group.items.map(item => {
                const Icon = item.icon;
                return <button key={item.id} className={`nav-item ${page === item.id ? "active" : ""}`} onClick={() => navigate(item.id)}><Icon size={18} /><span>{item.label}</span>{item.id === "subscriptions" && <span className="nav-badge">{subscriptions.length}</span>}</button>;
              })}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="help-card"><Sparkles size={18} /><strong>Need a hand?</strong><p>Visit our help center for tips and guides.</p><button onClick={() => alert("Help center coming soon!")}>Visit help center <ArrowRight size={14} /></button></div>
          <button className={`nav-item ${page === "settings" ? "active" : ""}`} onClick={() => navigate("settings")}><Settings size={18} /> Settings</button>
          <div className="profile"><Avatar name="Afra Hussain" /><div><strong>Afra Hussain</strong><span>Administrator</span></div><MoreHorizontal size={19} /></div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="topbar-left"><button className="mobile-menu icon-button" onClick={() => setMobileOpen(true)}><Menu size={21} /></button><span className="breadcrumb">Workspace <span>/</span> <strong>{pageTitles[page]}</strong></span></div>
          <div className="topbar-right">
            <div className="search-box"><Search size={17} /><input placeholder="Search anything..." value={search} onChange={e => setSearch(e.target.value)} /><kbd>⌘ K</kbd></div>
            <button className="notification-button" title="Notifications"><Bell size={19} /><i /></button>
            <Avatar name="Afra Hussain" />
          </div>
        </header>

        <div className="page-content">
          {page === "dashboard" && <Dashboard subscriptions={subscriptions} setPage={navigate} />}
          {page === "subscriptions" && <SubscriptionsPage subscriptions={visibleSubscriptions} setSubscriptions={setSubscriptions} openModal={() => setModal(true)} />}
          {page === "plans" && <PlansPage openModal={() => setModal(true)} />}
          {page === "customers" && <CustomersPage />}
          {page === "invoices" && <InvoicesPage />}
          {page === "analytics" && <AnalyticsPage />}
          {page === "settings" && <SettingsPage />}
          <footer>© 2026 Subscribely. Built for smarter subscription management.</footer>
        </div>
      </main>
      {modal && <AddSubscriptionModal close={() => setModal(false)} add={s => setSubscriptions(old => [s, ...old])} />}
    </div>
  );
}
