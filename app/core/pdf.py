"""PDF generation for Invoices and Quotations using ReportLab.

Produces clean, professional, branded PDFs for Brightloop Subscriptions.
"""
import io
from datetime import datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _fmt(val) -> str:
    if val is None:
        return "0.00"
    if isinstance(val, (Decimal, float, int)):
        return f"{Decimal(str(val)):,.2f}"
    return str(val)


def generate_invoice_pdf(invoice) -> bytes:
    """Generate a printable PDF for an invoice."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
        fontName="Helvetica-Bold",
    )
    subtitle_style = ParagraphStyle(
        "SubTitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#64748b"),
    )
    section_style = ParagraphStyle(
        "SectionHead",
        parent=styles["Heading2"],
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1e293b"),
        fontName="Helvetica-Bold",
    )
    cell_style = ParagraphStyle(
        "Cell",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155"),
    )
    bold_cell_style = ParagraphStyle(
        "BoldCell",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0f172a"),
    )

    story = []

    # Header
    header_data = [
        [
            Paragraph("<b>BRIGHTLOOP SUBSCRIPTIONS</b>", title_style),
            Paragraph(f"<b>INVOICE: {invoice.number}</b>", title_style),
        ],
        [
            Paragraph("Billing & Revenue Management Platform<br/>Kochi, India", subtitle_style),
            Paragraph(
                f"Issue Date: {invoice.issue_date}<br/>"
                f"Due Date: {invoice.due_date}<br/>"
                f"Period: {invoice.period_start} to {invoice.period_end}",
                subtitle_style,
            ),
        ],
    ]
    header_table = Table(header_data, colWidths=[270, 270])
    header_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ])
    )
    story.append(header_table)
    story.append(Spacer(1, 15))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceAfter=15))

    # Meta banner (Status, Payment State, Customer)
    payment_state = getattr(invoice, "_payment_state", "unpaid")
    outstanding = getattr(invoice, "_outstanding", invoice.total - invoice.paid_amount)
    customer_label = f"Customer #{invoice.customer_id}"
    if hasattr(invoice, "customer") and invoice.customer:
        customer_label = f"{invoice.customer.name} ({invoice.customer.email})"

    meta_data = [
        [
            Paragraph(f"<b>Billed To:</b> {customer_label}", cell_style),
            Paragraph(f"<b>Status:</b> {invoice.status.upper()}", cell_style),
            Paragraph(f"<b>Payment State:</b> {payment_state.upper()}", cell_style),
        ]
    ]
    meta_table = Table(meta_data, colWidths=[220, 160, 160])
    meta_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("PADDING", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#e2e8f0")),
        ])
    )
    story.append(meta_table)
    story.append(Spacer(1, 15))

    # Line items
    story.append(Paragraph("Invoice Items", section_style))
    story.append(Spacer(1, 6))

    lines_data = [
        [
            Paragraph("<b>Description</b>", bold_cell_style),
            Paragraph("<b>Qty</b>", bold_cell_style),
            Paragraph("<b>Unit Price</b>", bold_cell_style),
            Paragraph("<b>Discount</b>", bold_cell_style),
            Paragraph("<b>Tax</b>", bold_cell_style),
            Paragraph("<b>Total</b>", bold_cell_style),
        ]
    ]

    for line in getattr(invoice, "lines", []):
        lines_data.append([
            Paragraph(line.description or f"Product #{line.product_id}", cell_style),
            Paragraph(str(line.quantity), cell_style),
            Paragraph(f"INR {_fmt(line.unit_price)}", cell_style),
            Paragraph(f"INR {_fmt(line.discount_amount)}", cell_style),
            Paragraph(f"INR {_fmt(line.tax_amount)}", cell_style),
            Paragraph(f"INR {_fmt(line.line_total)}", bold_cell_style),
        ])

    if len(lines_data) == 1:
        lines_data.append([
            Paragraph("Subscription service charge", cell_style),
            Paragraph("1", cell_style),
            Paragraph(f"INR {_fmt(invoice.subtotal)}", cell_style),
            Paragraph(f"INR {_fmt(invoice.discount_total)}", cell_style),
            Paragraph(f"INR {_fmt(invoice.tax_total)}", cell_style),
            Paragraph(f"INR {_fmt(invoice.total)}", bold_cell_style),
        ])

    lines_table = Table(lines_data, colWidths=[180, 50, 75, 75, 75, 85])
    lines_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("PADDING", (0, 0), (-1, -1), 6),
        ])
    )
    story.append(lines_table)
    story.append(Spacer(1, 15))

    # Totals table
    totals_data = [
        [Paragraph("Subtotal:", cell_style), Paragraph(f"INR {_fmt(invoice.subtotal)}", cell_style)],
        [Paragraph("Discount:", cell_style), Paragraph(f"- INR {_fmt(invoice.discount_total)}", cell_style)],
        [Paragraph("Tax:", cell_style), Paragraph(f"+ INR {_fmt(invoice.tax_total)}", cell_style)],
        [Paragraph("<b>Total:</b>", bold_cell_style), Paragraph(f"<b>INR {_fmt(invoice.total)}</b>", bold_cell_style)],
        [Paragraph("Paid Amount:", cell_style), Paragraph(f"INR {_fmt(invoice.paid_amount)}", cell_style)],
        [Paragraph("<b>Outstanding Balance:</b>", bold_cell_style), Paragraph(f"<b>INR {_fmt(outstanding)}</b>", bold_cell_style)],
    ]
    totals_table = Table(totals_data, colWidths=[150, 120])
    totals_table.setStyle(
        TableStyle([
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("PADDING", (0, 0), (-1, -1), 4),
            ("LINEABOVE", (0, 3), (1, 3), 1, colors.HexColor("#0f172a")),
            ("LINEABOVE", (0, 5), (1, 5), 1, colors.HexColor("#0f172a")),
            ("BACKGROUND", (0, 5), (1, 5), colors.HexColor("#f8fafc")),
        ])
    )

    wrapper_data = [
        [Paragraph("", cell_style), totals_table]
    ]
    wrapper_table = Table(wrapper_data, colWidths=[270, 270])
    wrapper_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(wrapper_table)

    # Payments if any
    payments = getattr(invoice, "payments", [])
    if payments:
        story.append(Spacer(1, 15))
        story.append(Paragraph("Recorded Payments", section_style))
        story.append(Spacer(1, 6))

        pay_data = [
            [
                Paragraph("<b>ID</b>", bold_cell_style),
                Paragraph("<b>Date</b>", bold_cell_style),
                Paragraph("<b>Method</b>", bold_cell_style),
                Paragraph("<b>Amount</b>", bold_cell_style),
                Paragraph("<b>Note</b>", bold_cell_style),
            ]
        ]
        for p in payments:
            pay_data.append([
                Paragraph(f"#{p.id}", cell_style),
                Paragraph(str(p.paid_at), cell_style),
                Paragraph(p.method.replace("_", " ").title(), cell_style),
                Paragraph(f"INR {_fmt(p.amount)}", bold_cell_style),
                Paragraph(p.note or "—", cell_style),
            ])

        pay_table = Table(pay_data, colWidths=[40, 80, 100, 100, 220])
        pay_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("PADDING", (0, 0), (-1, -1), 5),
            ])
        )
        story.append(pay_table)

    # Footer note
    story.append(Spacer(1, 20))
    story.append(
        Paragraph(
            "<i>Thank you for your business. For any billing queries, contact support@brightloop.io.</i>",
            subtitle_style,
        )
    )

    doc.build(story)
    return buffer.getvalue()


def generate_quotation_pdf(quotation) -> bytes:
    """Generate a printable PDF for a quotation."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
        fontName="Helvetica-Bold",
    )
    subtitle_style = ParagraphStyle(
        "SubTitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#64748b"),
    )
    section_style = ParagraphStyle(
        "SectionHead",
        parent=styles["Heading2"],
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1e293b"),
        fontName="Helvetica-Bold",
    )
    cell_style = ParagraphStyle(
        "Cell",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155"),
    )
    bold_cell_style = ParagraphStyle(
        "BoldCell",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0f172a"),
    )

    story = []

    created_date = (
        quotation.created_at.date()
        if hasattr(quotation.created_at, "date")
        else str(quotation.created_at)[:10]
    )
    valid_until = quotation.valid_until or "No expiry"

    # Header
    header_data = [
        [
            Paragraph("<b>BRIGHTLOOP SUBSCRIPTIONS</b>", title_style),
            Paragraph(f"<b>QUOTATION: {quotation.number}</b>", title_style),
        ],
        [
            Paragraph("Intelligent Recurring Revenue Platform<br/>Kochi, India", subtitle_style),
            Paragraph(
                f"Date: {created_date}<br/>"
                f"Valid Until: {valid_until}<br/>"
                f"Status: {quotation.status.upper()}",
                subtitle_style,
            ),
        ],
    ]
    header_table = Table(header_data, colWidths=[270, 270])
    header_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ])
    )
    story.append(header_table)
    story.append(Spacer(1, 15))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceAfter=15))

    # Meta banner
    customer_label = f"Customer #{quotation.customer_id}"
    if hasattr(quotation, "customer") and quotation.customer:
        customer_label = f"{quotation.customer.name} ({quotation.customer.email})"

    plan_label = f"Plan #{quotation.plan_id}"
    if hasattr(quotation, "plan") and quotation.plan:
        plan_label = quotation.plan.name

    meta_data = [
        [
            Paragraph(f"<b>Customer:</b> {customer_label}", cell_style),
            Paragraph(f"<b>Plan:</b> {plan_label}", cell_style),
            Paragraph(f"<b>Payment Terms:</b> {quotation.payment_terms or 'Immediate'}", cell_style),
        ]
    ]
    meta_table = Table(meta_data, colWidths=[240, 150, 150])
    meta_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("PADDING", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#e2e8f0")),
        ])
    )
    story.append(meta_table)
    story.append(Spacer(1, 15))

    # Lines
    story.append(Paragraph("Quotation Items", section_style))
    story.append(Spacer(1, 6))

    lines_data = [
        [
            Paragraph("<b>Product / Description</b>", bold_cell_style),
            Paragraph("<b>Qty</b>", bold_cell_style),
            Paragraph("<b>Unit Price</b>", bold_cell_style),
            Paragraph("<b>Tax</b>", bold_cell_style),
            Paragraph("<b>Total</b>", bold_cell_style),
        ]
    ]

    for line in getattr(quotation, "lines", []):
        desc = line.description or getattr(line, "product_name", None) or f"Product #{line.product_id}"
        lines_data.append([
            Paragraph(desc, cell_style),
            Paragraph(str(line.quantity), cell_style),
            Paragraph(f"INR {_fmt(line.unit_price)}", cell_style),
            Paragraph(f"INR {_fmt(getattr(line, 'tax_amount', 0))}", cell_style),
            Paragraph(f"INR {_fmt(line.line_total)}", bold_cell_style),
        ])

    lines_table = Table(lines_data, colWidths=[210, 50, 95, 85, 95])
    lines_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("PADDING", (0, 0), (-1, -1), 6),
        ])
    )
    story.append(lines_table)
    story.append(Spacer(1, 15))

    # Totals
    totals_data = [
        [Paragraph("Subtotal:", cell_style), Paragraph(f"INR {_fmt(quotation.subtotal)}", cell_style)],
        [Paragraph("Tax Total:", cell_style), Paragraph(f"+ INR {_fmt(quotation.tax_total)}", cell_style)],
        [Paragraph("<b>Quotation Total:</b>", bold_cell_style), Paragraph(f"<b>INR {_fmt(quotation.total)}</b>", bold_cell_style)],
    ]
    totals_table = Table(totals_data, colWidths=[150, 120])
    totals_table.setStyle(
        TableStyle([
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("PADDING", (0, 0), (-1, -1), 4),
            ("LINEABOVE", (0, 2), (1, 2), 1, colors.HexColor("#0f172a")),
            ("BACKGROUND", (0, 2), (1, 2), colors.HexColor("#f8fafc")),
        ])
    )

    wrapper_data = [[Paragraph("", cell_style), totals_table]]
    wrapper_table = Table(wrapper_data, colWidths=[270, 270])
    story.append(wrapper_table)

    # Footer note
    story.append(Spacer(1, 20))
    story.append(
        Paragraph(
            "<i>This quotation is valid until the expiration date listed above. Once accepted, it converts to an active recurring subscription.</i>",
            subtitle_style,
        )
    )

    doc.build(story)
    return buffer.getvalue()
