"""Seed Part A: users, products, variants, plans, taxes, discounts, quote templates.

Safe to re-run: it only creates rows that don't exist yet (get-or-create).
Run from the project root:  python -m seeds.seed_catalog --customers 100
"""
import argparse
import random
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.core.security import hash_password
from app.auth.models import User
from app.catalog.models import (
    Product, ProductVariant, Plan, TaxRule, DiscountRule,
)
from app.quoting.models import QuoteTemplate, QuoteTemplateLine

SEED = 42
TODAY = date(2026, 10, 31)          # fixed so the data is identical every run
DEMO_PASSWORD = "Demo@12345"        # every seeded user logs in with this

FIRST = ["Aarav", "Diya", "Rohan", "Meera", "Kiran", "Anjali", "Vivek", "Sneha",
         "Arjun", "Priya", "Nikhil", "Lakshmi", "Farhan", "Neha", "Suresh", "Divya"]
COMPANY = ["Traders", "Technologies", "Solutions", "Retail", "Logistics", "Foods",
           "Consulting", "Industries", "Systems", "Enterprises", "Labs", "Stores"]
PLACE = ["Kochi", "Calicut", "Thrissur", "Kollam", "Palakkad", "Kannur", "Munnar", "Alappuzha"]


def d(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"))


def get_or_create(db, model, lookup: dict, extra: dict | None = None):
    """Return (object, created?). `lookup` identifies the row, `extra` fills new rows."""
    obj = db.execute(select(model).filter_by(**lookup)).scalars().first()
    if obj:
        return obj, False
    obj = model(**lookup, **(extra or {}))
    db.add(obj)
    db.flush()          # gets the new id without committing yet
    return obj, True


def seed(customers: int):
    random.seed(SEED)
    created = {k: 0 for k in
               ["users", "products", "variants", "plans", "taxes", "discounts", "templates"]}
    pw_hash = hash_password(DEMO_PASSWORD)   # hash ONCE (bcrypt is slow), reuse for all

    with Session(engine) as db:
        # ---------- users (admin is bootstrapped by Athul, so we skip admin) ----------
        for i in range(1, 3):
            _, new = get_or_create(db, User, {"email": f"staff{i}@brightloop.demo"},
                                   {"name": f"Staff Member {i}", "role": "staff",
                                    "password_hash": pw_hash, "is_active": True})
            created["users"] += new
        for i in range(1, customers + 1):
            name = f"{random.choice(FIRST)} {random.choice(COMPANY)} {random.choice(PLACE)}"
            _, new = get_or_create(db, User, {"email": f"customer{i:03d}@brightloop.demo"},
                                   {"name": name, "role": "customer",
                                    "password_hash": pw_hash, "is_active": True})
            created["users"] += new

        # ---------- products + variants ----------
        products_spec = [
            ("CloudPro", "subscription", 2000, 900, "Flagship cloud suite"),
            ("Brightloop CRM", "subscription", 1000, 400, "Customer relationship tool"),
            ("Brightloop Analytics", "subscription", 1500, 600, "Dashboards and reports"),
            ("Extra Seat", "addon", 300, 100, "Add-on seat for any product"),
            ("Premium Support Pack", "addon", 500, 150, "24x7 support add-on"),
        ]
        prod = {}
        for name, ptype, sale, cost, notes in products_spec:
            p, new = get_or_create(db, Product, {"name": name},
                                   {"type": ptype, "sales_price": d(sale),
                                    "cost_price": d(cost), "notes": notes, "is_active": True})
            prod[name] = p
            created["products"] += new

        variants_spec = [
            ("CloudPro", "Brand", "Standard", 0),
            ("CloudPro", "Brand", "Odoo", 560),       # the example from the problem statement
            ("CloudPro", "Edition", "Enterprise", 1200),
            ("Brightloop CRM", "Brand", "Standard", 0),
            ("Brightloop CRM", "Brand", "Odoo", 560),
            ("Brightloop Analytics", "Edition", "Pro", 400),
        ]
        for pname, attr, value, delta in variants_spec:
            _, new = get_or_create(db, ProductVariant,
                                   {"product_id": prod[pname].id, "attribute": attr, "value": value},
                                   {"price_delta": d(delta)})
            created["variants"] += new

        # ---------- plans: all four billing cycles + one closed plan ----------
        plans_spec = [
            ("Daily Trial", "daily", 50, 1, date(2026, 1, 1), None, "active"),
            ("Weekly Starter", "weekly", 300, 1, date(2026, 1, 1), None, "active"),
            ("Monthly Standard", "monthly", 1000, 1, date(2026, 1, 1), None, "active"),
            ("Monthly Team (10+ seats)", "monthly", 1000, 10, date(2026, 1, 1), None, "active"),
            ("Yearly Business", "yearly", 10000, 1, date(2026, 1, 1), None, "active"),
            ("Legacy Monthly 2025", "monthly", 800, 1, date(2025, 1, 1), date(2025, 12, 31), "closed"),
        ]
        plan = {}
        for name, cycle, price, minq, avail_from, avail_to, status in plans_spec:
            p, new = get_or_create(db, Plan, {"name": name},
                                   {"billing_cycle": cycle, "price": d(price), "min_quantity": minq,
                                    "available_from": avail_from, "available_to": avail_to,
                                    "auto_close": avail_to is not None,
                                    "allow_early_close": True, "allow_pause": True,
                                    "allow_renew": status == "active", "status": status})
            plan[name] = p
            created["plans"] += new

        # ---------- tax rules (rate is a percent; lower priority number wins) ----------
        gst18, new = get_or_create(db, TaxRule, {"name": "GST 18% (global)"},
                                   {"rate": d(18), "product_id": None, "priority": 10,
                                    "tax_included": False, "is_active": True})
        created["taxes"] += new
        _, new = get_or_create(db, TaxRule, {"name": "GST 5% (Support Pack)"},
                               {"rate": d(5), "product_id": prod["Premium Support Pack"].id,
                                "priority": 5, "tax_included": False, "is_active": True})
        created["taxes"] += new

        # ---------- discount rules ----------
        discounts_spec = [
            # name, type, value, min_purchase, min_qty, starts, ends, limit, used, scope, product
            ("Volume 10% (10+ seats)", "percentage", 10, None, 10, date(2026, 1, 1), None, 100, 12, "subscription", None),
            # EXPIRED on purpose: this drives the Revenue Guardian anomaly demo
            ("Launch Offer Rs500 off", "fixed", 500, None, None, date(2026, 1, 1), date(2026, 9, 30), 200, 64, "subscription", None),
            # EXHAUSTED on purpose: usage_limit reached, must not apply
            ("Early Bird 5%", "percentage", 5, None, None, date(2026, 1, 1), None, 10, 10, "subscription", None),
            ("CRM Loyalty 15%", "percentage", 15, 2000, None, date(2026, 6, 1), date(2027, 6, 1), 50, 3, "product", "Brightloop CRM"),
        ]
        for name, dtype, value, minp, minq, starts, ends, limit, used, scope, pname in discounts_spec:
            _, new = get_or_create(db, DiscountRule, {"name": name},
                                   {"type": dtype, "value": d(value),
                                    "min_purchase": d(minp) if minp else None,
                                    "min_quantity": minq, "starts_at": starts, "ends_at": ends,
                                    "usage_limit": limit, "used_count": used, "scope": scope,
                                    "product_id": prod[pname].id if pname else None,
                                    "is_active": True})
            created["discounts"] += new

        # ---------- quote templates ----------
        templates_spec = [
            ("Professional Plan Offer", 7, "Net 15", "Monthly Team (10+ seats)",
             [("CloudPro", 10, 2000), ("Premium Support Pack", 1, 500)]),
            ("Starter Offer", 14, "Net 30", "Monthly Standard",
             [("Brightloop CRM", 1, 1000)]),
        ]
        for tname, days, terms, plan_name, lines in templates_spec:
            tpl, new = get_or_create(db, QuoteTemplate, {"name": tname},
                                     {"validity_days": days, "payment_terms": terms,
                                      "plan_id": plan[plan_name].id, "is_active": True})
            if new:
                created["templates"] += 1
                for pname, qty, price in lines:
                    db.add(QuoteTemplateLine(template_id=tpl.id, product_id=prod[pname].id,
                                             quantity=qty, unit_price=d(price),
                                             tax_rule_id=gst18.id))

        db.commit()

    print("Seed Part A finished. New rows created:")
    for k, v in created.items():
        print(f"  {k}: {v}")
    print(f"Demo login for every seeded user: password {DEMO_PASSWORD}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--customers", type=int, default=100)
    args = ap.parse_args()
    seed(args.customers)