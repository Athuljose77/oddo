"""billing engine: runs, attempts, invoices, lines, discount redemptions, payments

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-31

Idempotency constraints (docs/CONVENTIONS.md):
- invoices UNIQUE(subscription_id, period_start)
- billing_runs partial UNIQUE(status) WHERE status='running'  (one run at a time)
- billing_attempts UNIQUE(run_id, subscription_id, period_start)
- discount_redemptions UNIQUE(discount_rule_id, invoice_id)
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="running"),
        sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("projected_subtotal", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("projected_tax", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("projected_discount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("projected_total", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("catchup_subscriptions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("catchup_max_periods", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("triggered_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # One run at a time: partial unique index on the running status
    op.create_index(
        "uq_billing_runs_one_running",
        "billing_runs",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
        sqlite_where=sa.text("status = 'running'"),
    )

    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.String(length=20), nullable=False, unique=True),
        sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id"), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("billing_runs.id"), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="draft"),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("discount_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("paid_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_printed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # THE idempotency guarantee: one invoice per subscription per period
        sa.UniqueConstraint("subscription_id", "period_start", name="uq_invoice_subscription_period"),
    )
    op.create_index("ix_invoices_subscription_id", "invoices", ["subscription_id"])
    op.create_index("ix_invoices_customer_id", "invoices", ["customer_id"])
    op.create_index("ix_invoices_run_id", "invoices", ["run_id"])

    op.create_table(
        "billing_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("billing_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("discount_rule_name", sa.String(length=120), nullable=True),
        sa.Column("projected_subtotal", sa.Numeric(12, 2), nullable=True),
        sa.Column("projected_tax", sa.Numeric(12, 2), nullable=True),
        sa.Column("projected_discount", sa.Numeric(12, 2), nullable=True),
        sa.Column("projected_total", sa.Numeric(12, 2), nullable=True),
        sa.Column("actual_total", sa.Numeric(12, 2), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("run_id", "subscription_id", "period_start", name="uq_attempt_period"),
    )
    op.create_index("ix_billing_attempts_run_id", "billing_attempts", ["run_id"])
    op.create_index("ix_billing_attempts_subscription_id", "billing_attempts", ["subscription_id"])

    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "invoice_id",
            sa.Integer(),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("variant_id", sa.Integer(), sa.ForeignKey("product_variants.id"), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_rule_id", sa.Integer(), sa.ForeignKey("tax_rules.id"), nullable=True),
        sa.Column("tax_rate", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )
    op.create_index("ix_invoice_lines_invoice_id", "invoice_lines", ["invoice_id"])

    op.create_table(
        "discount_redemptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "discount_rule_id",
            sa.Integer(),
            sa.ForeignKey("discount_rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            sa.Integer(),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("discount_rule_id", "invoice_id", name="uq_redemption_rule_invoice"),
    )
    op.create_index("ix_discount_redemptions_discount_rule_id", "discount_redemptions", ["discount_rule_id"])
    op.create_index("ix_discount_redemptions_invoice_id", "discount_redemptions", ["invoice_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "invoice_id",
            sa.Integer(),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("paid_at", sa.Date(), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])


def downgrade() -> None:
    op.drop_table("payments")
    op.drop_table("discount_redemptions")
    op.drop_table("invoice_lines")
    op.drop_table("billing_attempts")
    op.drop_table("invoices")
    op.drop_index("uq_billing_runs_one_running", table_name="billing_runs")
    op.drop_table("billing_runs")