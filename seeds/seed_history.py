"""Seed Part B: subscriptions, invoices, payments + 3 demo anomalies (bulk inserts).

Run:   python -m seeds.seed_history                 (first run, or "already seeded" check)
       python -m seeds.seed_history --reset         (delete OUR seed rows, rebuild)
Small test:  python -m seeds.seed_history --subscriptions 200 --invoices 800 --payments 700 --reset

Rules: deterministic (random.Random(seed)), Decimal money, never touches rows that are not
ours (our numbers start SUB-S-/SUB-D-/INV-S-/INV-D-), one transaction (all or nothing).
"""
import argparse
import importlib
import random
import sys
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, func, insert, select, text

for _m in ("app.auth.models", "app.catalog.models", "app.quoting.models",
           "app.subscriptions.models", "app.billing.models"):
    importlib.import_module(_m)
from app.core.database import Base, engine  # noqa: E402

T = Base.metadata.tables
UTC = timezone.utc
D0 = Decimal("0.00")
CYCLE_DAYS = {"daily": 1, "weekly": 7, "monthly": 30, "yearly": 365}


def q2(x):
    return Decimal(x).quantize(Decimal("0.01"), ROUND_HALF_UP)


def kind_of(cycle: str) -> str:
    c = (cycle or "").lower()
    if c.startswith("d"):
        return "daily"
    if c.startswith("w"):
        return "weekly"
    if c.startswith("m"):
        return "monthly"
    return "yearly"


def add_months(d: date, k: int) -> date:
    total = d.year * 12 + (d.month - 1) + k
    y, m = divmod(total, 12)
    m += 1
    return date(y, m, min(d.day, monthrange(y, m)[1]))  # Jan-31 anchor clamps to month end


def period_start(kind, anchor, k):
    if kind == "monthly":
        return add_months(anchor, k)
    if kind == "yearly":
        return add_months(anchor, 12 * k)
    if kind == "weekly":
        return anchor + timedelta(days=7 * k)
    return anchor + timedelta(days=k)


def to_date(v):
    if v is None:
        return None
    return v.date() if isinstance(v, datetime) else v


def dt(d: date) -> datetime:
    return datetime.combine(d, time(9, 0), tzinfo=UTC)


def chunks(rows, n):
    for i in range(0, len(rows), n):
        yield rows[i:i + n]


# ---------------------------------------------------------------- reset
def seed_sub_ids(conn):
    s = T["subscriptions"]
    return select(s.c.id).where(s.c.number.like("SUB-S-%") | s.c.number.like("SUB-D-%"))


def has_seed(conn):
    return conn.execute(select(func.count()).select_from(seed_sub_ids(conn).subquery())).scalar() > 0


def reset_seed(conn):
    sub_ids = seed_sub_ids(conn)
    inv_ids = select(T["invoices"].c.id).where(T["invoices"].c.subscription_id.in_(sub_ids))
    conn.execute(delete(T["discount_redemptions"]).where(T["discount_redemptions"].c.invoice_id.in_(inv_ids)))
    conn.execute(delete(T["payments"]).where(T["payments"].c.invoice_id.in_(inv_ids)))
    conn.execute(delete(T["invoice_lines"]).where(T["invoice_lines"].c.invoice_id.in_(inv_ids)))
    conn.execute(delete(T["billing_attempts"]).where(T["billing_attempts"].c.subscription_id.in_(sub_ids)))
    conn.execute(delete(T["invoices"]).where(T["invoices"].c.subscription_id.in_(sub_ids)))
    conn.execute(delete(T["subscription_events"]).where(T["subscription_events"].c.subscription_id.in_(sub_ids)))
    conn.execute(delete(T["subscription_lines"]).where(T["subscription_lines"].c.subscription_id.in_(sub_ids)))
    conn.execute(delete(T["subscriptions"]).where(T["subscriptions"].c.id.in_(sub_ids)))


# ---------------------------------------------------------------- generator
class Gen:
    def __init__(self, conn, args):
        self.args = args
        self.rng = random.Random(args.seed)
        self.as_of = date.fromisoformat(args.as_of)
        self.ids = {}
        for t in ("subscriptions", "subscription_lines", "subscription_events", "invoices",
                  "invoice_lines", "discount_redemptions", "payments"):
            self.ids[t] = conn.execute(select(func.coalesce(func.max(T[t].c.id), 0))).scalar()
        self.rows = {t: [] for t in self.ids}
        self.inv_seq = 0
        self.load_reference(conn)

    def nid(self, t):
        self.ids[t] += 1
        return self.ids[t]

    def load_reference(self, conn):
        u, p, pl = T["users"], T["products"], T["plans"]
        self.customers = [r[0] for r in conn.execute(
            select(u.c.id).where(u.c.role == "customer", u.c.email.like("customer%@brightloop.demo")).order_by(u.c.id))]
        self.products = [dict(r._mapping) for r in conn.execute(
            select(p.c.id, p.c.name, p.c.sales_price).where(p.c.is_active.is_(True)).order_by(p.c.id))]
        plans = [dict(r._mapping) for r in conn.execute(
            select(pl.c.id, pl.c.name, pl.c.billing_cycle, pl.c.price, pl.c.min_quantity, pl.c.status).order_by(pl.c.id))]
        plans = [x for x in plans if "smoke" not in (x["name"] or "").lower()]  # skip Athul's test plans
        self.products = [x for x in self.products if "smoke" not in (x["name"] or "").lower()]
        for x in plans:
            x["kind"] = kind_of(x["billing_cycle"])
        self.legacy_plans = [x for x in plans if (x["status"] or "").lower() == "closed"]
        self.plans = [x for x in plans if (x["status"] or "").lower() != "closed"]
        self.tax_rules = [dict(r._mapping) for r in conn.execute(
            select(T["tax_rules"].c.id, T["tax_rules"].c.rate, T["tax_rules"].c.product_id,
                   T["tax_rules"].c.priority).where(T["tax_rules"].c.is_active.is_(True)))]
        dr = T["discount_rules"]
        self.discounts = [dict(r._mapping) for r in conn.execute(
            select(dr.c.id, dr.c.type, dr.c.value, dr.c.starts_at, dr.c.ends_at, dr.c.usage_limit,
                   dr.c.used_count, dr.c.is_active).order_by(dr.c.id))]
        for x in self.discounts:
            x["s"], x["e"] = to_date(x["starts_at"]), to_date(x["ends_at"])
        self.expired_rule = next((x for x in self.discounts if x["e"] and x["e"] < self.as_of), None)
        self.usable_rules = [x for x in self.discounts if x["is_active"] and x["type"] in ("fixed", "percentage")
                             and not (x["usage_limit"] is not None and x["used_count"] >= x["usage_limit"])]

    def tax_for(self, product_id):
        specific = [t for t in self.tax_rules if t["product_id"] == product_id]
        pool = specific or [t for t in self.tax_rules if t["product_id"] is None]
        if not pool:
            return None, Decimal("0")
        t = min(pool, key=lambda t: t["priority"])
        return t["id"], Decimal(t["rate"])

    @staticmethod
    def discount_amount(rule, net):
        if rule["type"] == "percentage":
            return q2(net * Decimal(rule["value"]) / 100)
        return min(q2(rule["value"]), net)

    def valid_rule_on(self, d):
        ok = [r for r in self.usable_rules if (r["s"] is None or r["s"] <= d) and (r["e"] is None or r["e"] >= d)]
        return self.rng.choice(ok) if ok else None

    # ------------------------------------------------------------ one subscription (+lines, event, invoices)
    def build_sub(self, number, inv_number, customer, plan, status, anchor, n_inv, qty, add_on,
                  next_billing, expiry, terms, paused_at=None, closed_at=None, forced_rule=None):
        rng, kind = self.rng, plan["kind"]
        sid = self.nid("subscriptions")
        prod = rng.choice(self.products)
        specs = [(prod, qty, Decimal(plan["price"]))]
        if add_on and len(self.products) > 1:
            other = rng.choice([p for p in self.products if p["id"] != prod["id"]])
            specs.append((other, 1, Decimal(other["sales_price"] or 10)))
        lines = []
        for p, qn, price in specs:
            rule_id, rate = self.tax_for(p["id"])
            net = q2(price * qn)
            tax = q2(net * rate / 100)
            lines.append(dict(product=p, qty=qn, price=q2(price), rule_id=rule_id, rate=rate, net=net, tax=tax))
        sub_net = sum(l["net"] for l in lines)
        sub_tax = sum(l["tax"] for l in lines)
        start = anchor if n_inv else (anchor)
        created = dt(min(start, self.as_of))
        self.rows["subscriptions"].append(dict(
            id=sid, number=number, customer_id=customer, plan_id=plan["id"], quotation_id=None, created_by=None,
            start_date=anchor, anchor_date=anchor, expiry_date=expiry, payment_terms=f"Net {terms}",
            next_billing_date=next_billing,
            last_billing_date=period_start(kind, anchor, n_inv - 1) if n_inv else None,
            period_index=n_inv, status=status, subtotal=sub_net, tax_total=sub_tax, total=sub_net + sub_tax,
            paused_at=paused_at, pause_reason="seed: paused" if paused_at else None,
            closed_at=closed_at, close_reason="seed: closed" if closed_at else None,
            created_at=created, updated_at=created))
        for l in lines:
            self.rows["subscription_lines"].append(dict(
                id=self.nid("subscription_lines"), subscription_id=sid, product_id=l["product"]["id"],
                variant_id=None, description=l["product"]["name"], quantity=l["qty"], unit_price=l["price"],
                tax_rule_id=l["rule_id"], tax_rate=l["rate"], tax_amount=l["tax"], line_total=l["net"] + l["tax"]))
        self.rows["subscription_events"].append(dict(
            id=self.nid("subscription_events"), subscription_id=sid, from_status=None, to_status=status,
            actor_id=None, note="seeded", created_at=created))
        for k in range(n_inv):
            ps = period_start(kind, anchor, k)
            pe = period_start(kind, anchor, k + 1) - timedelta(days=1)
            rule = forced_rule if (forced_rule and k == n_inv - 1) else (
                self.valid_rule_on(ps) if rng.random() < 0.06 else None)
            iid = self.nid("invoices")
            inv_lines, subtotal, disc_t, tax_t = [], D0, D0, D0
            for li, l in enumerate(lines):
                d = self.discount_amount(rule, l["net"]) if (rule and li == 0) else D0
                tax = q2((l["net"] - d) * l["rate"] / 100)
                inv_lines.append(dict(
                    id=self.nid("invoice_lines"), invoice_id=iid, product_id=l["product"]["id"], variant_id=None,
                    description=l["product"]["name"], quantity=l["qty"], unit_price=l["price"], discount_amount=d,
                    tax_rule_id=l["rule_id"], tax_rate=l["rate"], tax_amount=tax, line_total=l["net"] - d + tax))
                subtotal += l["net"]; disc_t += d; tax_t += tax
            self.rows["invoice_lines"].extend(inv_lines)
            if rule:
                self.rows["discount_redemptions"].append(dict(
                    id=self.nid("discount_redemptions"), discount_rule_id=rule["id"], invoice_id=iid,
                    amount=disc_t, created_at=dt(ps)))
            self.rows["invoices"].append(dict(
                id=iid, number=inv_number(k), subscription_id=sid, customer_id=customer, run_id=None,
                period_start=ps, period_end=pe, issue_date=ps, due_date=ps + timedelta(days=terms),
                status="confirmed", subtotal=subtotal, tax_total=tax_t, discount_total=disc_t,
                total=subtotal - disc_t + tax_t, paid_amount=D0, sent_at=None, last_printed_at=None,
                created_at=dt(ps), updated_at=dt(ps)))

    # ------------------------------------------------------------ demo anomalies
    def build_demos(self):
        rng, as_of = self.rng, self.as_of
        monthly = [p for p in self.plans if p["kind"] == "monthly"] or self.plans
        cust = rng.sample(self.customers, 3)
        info = {}

        # 1) expired-discount: last invoice still carries a discount rule that had already ended
        if self.expired_rule:
            last = min(as_of, self.expired_rule["e"] + timedelta(days=10))
            last = date(last.year, last.month, min(last.day, 28))
            n = 8
            anchor = add_months(last, -(n - 1))
            plan = monthly[0]
            self.build_sub("SUB-D-EXPDISC", lambda k: f"INV-D-EXP-{k+1:02d}", cust[0], plan, "active", anchor, n,
                           2, False, period_start("monthly", anchor, n), None, 15, forced_rule=self.expired_rule)
            info["expired_discount"] = f"SUB-D-EXPDISC (last invoice {last} used a discount that ended {self.expired_rule['e']})"
        else:
            info["expired_discount"] = "SKIPPED (no expired discount rule found; run seed_catalog first)"

        # 2) paused-but-due: status paused although its next billing date is already in the past
        last = as_of - timedelta(days=41)
        last = date(last.year, last.month, min(last.day, 28))
        n = 6
        anchor = add_months(last, -(n - 1))
        nb = period_start("monthly", anchor, n)
        if nb >= as_of:
            nb = as_of - timedelta(days=5)
        self.build_sub("SUB-D-PAUSED", lambda k: f"INV-D-PSD-{k+1:02d}", cust[1], monthly[0], "paused", anchor, n,
                       1, False, nb, None, 15, paused_at=dt(as_of - timedelta(days=35)))
        info["paused_due"] = f"SUB-D-PAUSED (paused, next billing {nb} is in the past)"

        # 3) Jan-31 anchored monthly: periods Jan 31, Feb 28, Mar 31, Apr 30 ...
        anchor = date(as_of.year - 1, 1, 31)
        n = 0
        while period_start("monthly", anchor, n) <= as_of:
            n += 1
        self.build_sub("SUB-D-JAN31", lambda k: f"INV-D-J31-{k+1:02d}", cust[2], monthly[0], "active", anchor, n,
                       1, False, period_start("monthly", anchor, n), None, 15)
        info["jan31"] = f"SUB-D-JAN31 (anchor {anchor}, {n} invoices, clamped to month end)"
        return info

    # ------------------------------------------------------------ generic subscriptions
    def build_generic(self, n_subs, invoice_target):
        rng, as_of, months = self.rng, self.as_of, self.args.months
        kinds = {}
        for p in self.plans:
            kinds.setdefault(p["kind"], []).append(p)
        kind_w = {"monthly": 70, "yearly": 14, "weekly": 9, "daily": 7}
        ks = [k for k in kind_w if k in kinds]
        specs = []
        for i in range(n_subs):
            status = rng.choices(["active", "paused", "closed", "confirmed", "draft"], [72, 7, 15, 4, 2])[0]
            if status == "closed" and self.legacy_plans and rng.random() < 0.4:
                plan = rng.choice(self.legacy_plans)
            else:
                plan = rng.choice(kinds[rng.choices(ks, [kind_w[k] for k in ks])[0]])
            kind = plan["kind"]
            billed = status in ("active", "paused", "closed")
            last = None
            cap = 0
            if billed:
                cd = CYCLE_DAYS[kind]
                back = rng.randint(35, 300) if status == "closed" else rng.randint(0, cd - 1)
                last = as_of - timedelta(days=back)
                if kind in ("monthly", "yearly"):
                    last = date(last.year, last.month, min(last.day, 28))
                left_days = months * 30 - (as_of - last).days
                cap = {"monthly": left_days // 30 + 1, "weekly": min(20, left_days // 7 + 1),
                       "daily": min(14, left_days + 1), "yearly": 2 if left_days >= 365 else 1}[kind]
                cap = max(1, min(cap, months if kind == "monthly" else cap))
            specs.append(dict(status=status, plan=plan, kind=kind, billed=billed, last=last, cap=cap, n=1 if billed else 0))
        billed_idx = [i for i, s in enumerate(specs) if s["billed"]]
        remaining = invoice_target - len(billed_idx)
        pool = [i for i in billed_idx if specs[i]["n"] < specs[i]["cap"] and specs[i]["kind"] != "yearly"]
        while remaining > 0 and pool:
            j = rng.randrange(len(pool))
            s = specs[pool[j]]
            s["n"] += 1
            remaining -= 1
            if s["n"] >= s["cap"]:
                pool[j] = pool[-1]
                pool.pop()
        if remaining > 0:
            print(f"  note: could not reach invoice target, {remaining} short (raise --months or subscriptions)")
        for i, s in enumerate(specs):
            plan, kind, status = s["plan"], s["kind"], s["status"]
            cust = rng.choice(self.customers)
            terms = rng.choice([15, 15, 30])
            qty = rng.randint(max(plan["min_quantity"] or 1, 1), max(plan["min_quantity"] or 1, 1) + (15 if (plan["min_quantity"] or 1) > 1 else 4))
            add_on = rng.random() < 0.2
            expiry = None
            r = rng.random()
            if r < 0.04:
                expiry = as_of + timedelta(days=rng.randint(3, 30))
            elif r < 0.25:
                expiry = as_of + timedelta(days=rng.randint(31, 400))
            n = s["n"]
            paused_at = closed_at = None
            if s["billed"]:
                last = s["last"]
                if kind == "monthly":
                    anchor = add_months(last, -(n - 1))
                elif kind == "yearly":
                    anchor = add_months(last, -12 * (n - 1))
                elif kind == "weekly":
                    anchor = last - timedelta(days=7 * (n - 1))
                else:
                    anchor = last - timedelta(days=n - 1)
                nb = period_start(kind, anchor, n)
                if status == "paused":
                    paused_at = dt(as_of - timedelta(days=rng.randint(1, 20)))
                if status == "closed":
                    nb = None
                    closed_at = dt(last + timedelta(days=rng.randint(5, 25)))
                    expiry = None
            else:
                anchor = as_of + timedelta(days=rng.randint(1, 40))
                nb = anchor if status == "confirmed" else None
            self.build_sub(f"SUB-S-{i+1:05d}", self._inv_no, cust, plan, status, anchor, n, qty, add_on,
                           nb, expiry, terms, paused_at, closed_at)

    def _inv_no(self, k):
        self.inv_seq += 1
        return f"INV-S-{self.inv_seq:06d}"

    # ------------------------------------------------------------ payments
    def build_payments(self, payment_target):
        rng, as_of = self.rng, self.as_of
        inv = self.rows["invoices"]
        late_p = {c: rng.choices([0.05, 0.3, 0.7], [70, 20, 10])[0] for c in self.customers}
        jitter = [rng.uniform(0, 150) for _ in inv]
        order = sorted(range(len(inv)), key=lambda i: inv[i]["issue_date"].toordinal() + jitter[i])
        F = int(payment_target / 1.045)
        n_split, n_part = round(0.03 * F), round(0.015 * F)
        F += payment_target - (F + n_split + n_part)
        F = max(0, min(F, len(inv)))
        n_part = min(n_part, len(inv) - F)
        n_split = min(n_split, F)
        chosen = order[:F + n_part]
        rng.shuffle(chosen)
        partial, rest = chosen[:n_part], chosen[n_part:]
        split = set(rest[:n_split])
        methods = ["bank_transfer", "upi", "card", "cash", "cheque", "other"]
        mw = [35, 30, 25, 4, 4, 2]

        def pay(i, amount, when):
            self.rows["payments"].append(dict(
                id=self.nid("payments"), invoice_id=inv[i]["id"], amount=q2(amount),
                method=rng.choices(methods, mw)[0], paid_at=when, note=None, recorded_by=None, created_at=dt(when)))

        def when_for(i):
            iv = inv[i]
            if rng.random() < late_p[iv["customer_id"]]:
                w = iv["due_date"] + timedelta(days=rng.randint(1, 30))
            else:
                w = iv["issue_date"] + timedelta(days=rng.randint(0, (iv["due_date"] - iv["issue_date"]).days))
            return min(w, as_of)

        for i in rest:
            iv = inv[i]
            w = when_for(i)
            if i in split:
                first = q2(iv["total"] * Decimal(str(round(rng.uniform(0.4, 0.6), 2))))
                pay(i, first, w)
                pay(i, iv["total"] - first, min(as_of, w + timedelta(days=rng.randint(1, 20))))
            else:
                pay(i, iv["total"], w)
            iv["status"], iv["paid_amount"] = "paid", iv["total"]
        for i in partial:
            iv = inv[i]
            part = q2(iv["total"] * Decimal(str(round(rng.uniform(0.4, 0.7), 2))))
            pay(i, part, when_for(i))
            iv["paid_amount"] = part


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subscriptions", type=int, default=5200)
    ap.add_argument("--invoices", type=int, default=22000)
    ap.add_argument("--payments", type=int, default=20000)
    ap.add_argument("--months", type=int, default=24)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--as-of", default="2026-10-31")
    ap.add_argument("--chunk", type=int, default=2000)
    ap.add_argument("--reset", action="store_true", help="delete OUR seed rows (SUB-S-/SUB-D-) first")
    args = ap.parse_args()

    with engine.begin() as conn:
        if has_seed(conn):
            if not args.reset:
                print("Seed Part B data already exists. Nothing changed. Use --reset to rebuild it.")
                return
            reset_seed(conn)
            print("Deleted old seed rows (only SUB-S-/SUB-D- and what hangs off them).")
        g = Gen(conn, args)
        if not g.customers or not g.products or not g.plans:
            sys.exit("Need customers, products and plans first: run seeds.seed_catalog.")
        if len(g.customers) < 200:
            print(f"  warning: only {len(g.customers)} customers. Run seed_catalog --customers 1500 for realistic spread.")
        print("Billing cycles found:", {p["name"]: p["kind"] for p in g.plans + g.legacy_plans})
        demo = g.build_demos()
        demo_inv = len(g.rows["invoices"])
        g.build_generic(args.subscriptions - 3, args.invoices - demo_inv)
        g.build_payments(args.payments)

        seen = set()
        for iv in g.rows["invoices"]:
            key = (iv["subscription_id"], iv["period_start"])
            assert key not in seen, f"duplicate period {key}"
            seen.add(key)

        for t in ("subscriptions", "subscription_lines", "subscription_events", "invoices",
                  "invoice_lines", "discount_redemptions", "payments"):
            for part in chunks(g.rows[t], args.chunk):
                conn.execute(insert(T[t]), part)
            print(f"  inserted {t}: {len(g.rows[t])}")
        if engine.dialect.name == "postgresql":
            for t in g.rows:
                conn.execute(text(f"SELECT setval(pg_get_serial_sequence('{t}','id'), "
                                  f"(SELECT COALESCE(MAX(id),1) FROM {t}))"))

    inv = g.rows["invoices"]
    status = {}
    for s in g.rows["subscriptions"]:
        status[s["status"]] = status.get(s["status"], 0) + 1
    print("\nSeed Part B finished.")
    print(f"  subscriptions {len(g.rows['subscriptions'])} {status}")
    print(f"  invoices {len(inv)} | payments {len(g.rows['payments'])}")
    print(f"  unpaid/partial invoices {sum(1 for i in inv if i['status'] != 'paid')}")
    for v in demo.values():
        print("  demo:", v)


if __name__ == "__main__":
    main()
