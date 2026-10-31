"""Quotation endpoints. Staff create/manage; customers see and accept their own."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin, require_staff
from app.core.pagination import paginate
from app.quoting import service
from app.quoting.models import Quotation, QuotationLine, QuoteTemplate, QuoteTemplateLine
from app.quoting.schemas import (
    ConfirmOut,
    QuotationCreateIn,
    QuotationLineIn,
    QuotationOut,
    QuotationPatchIn,
    TemplateCreateIn,
    TemplateOut,
    TemplatePatchIn,
)

router = APIRouter(prefix="/api/v1", tags=["quoting"])


def _template_or_404(db: Session, template_id: int) -> QuoteTemplate:
    template = db.get(QuoteTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    return template


def _quotation_visible(db: Session, quotation_id: int, user) -> Quotation:
    """Staff see everything; customers see only their own (404 otherwise)."""
    q = db.get(Quotation, quotation_id)
    if q is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quotation not found")
    if user.role == "customer" and q.customer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quotation not found")
    return q


# ------------------------------------------------------------ templates
@router.get("/quote-templates", response_model=list[TemplateOut])
def list_templates(
    db: Session = Depends(get_db),
    _: object = Depends(require_staff),
):
    return db.scalars(select(QuoteTemplate).order_by(QuoteTemplate.id)).all()


@router.post("/quote-templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: TemplateCreateIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    data = payload.model_dump(exclude={"lines"})
    template = QuoteTemplate(**data)
    db.add(template)
    db.flush()
    for line in payload.lines:
        template.lines.append(QuoteTemplateLine(**line.model_dump()))
    db.commit()
    db.refresh(template)
    return template


@router.get("/quote-templates/{template_id}", response_model=TemplateOut)
def get_template(
    template_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_staff),
):
    return _template_or_404(db, template_id)


@router.patch("/quote-templates/{template_id}", response_model=TemplateOut)
def patch_template(
    template_id: int,
    payload: TemplatePatchIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    template = _template_or_404(db, template_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(template, key, value)
    db.commit()
    db.refresh(template)
    return template


# ------------------------------------------------------------ quotations
@router.get("/quotations")
def list_quotations(
    quote_status: str | None = Query(None, alias="status"),
    customer_id: int | None = None,
    q: str | None = Query(None, min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    stmt = select(Quotation)
    if user.role == "customer":
        stmt = stmt.where(Quotation.customer_id == user.id)  # forced server-side scope
    elif customer_id:
        stmt = stmt.where(Quotation.customer_id == customer_id)
    if quote_status:
        stmt = stmt.where(Quotation.status == quote_status)
    if q:
        stmt = stmt.where(Quotation.number.ilike(f"%{q}%"))
    return paginate(db, stmt.order_by(Quotation.id.desc()), page, page_size)


@router.post("/quotations", response_model=QuotationOut, status_code=status.HTTP_201_CREATED)
def create_quotation(
    payload: QuotationCreateIn,
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    from app.auth.models import User
    from app.catalog.models import Plan

    customer = db.get(User, payload.customer_id)
    if customer is None or customer.role != "customer":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "customer_id must reference a customer")
    if payload.plan_id is not None and db.get(Plan, payload.plan_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "plan_id not found")

    template = None
    if payload.template_id is not None:
        template = _template_or_404(db, payload.template_id)

    # Lines: explicit wins; otherwise template lines; otherwise 422
    if payload.lines is not None:
        raw_lines = payload.lines
    elif template is not None and template.lines:
        raw_lines = [
            QuotationLineIn(
                product_id=l.product_id, quantity=l.quantity, unit_price=l.unit_price, tax_rule_id=l.tax_rule_id
            )
            for l in template.lines
        ]
    else:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Provide lines or use a template that contains lines",
        )

    resolved = service.resolve_lines(db, raw_lines)

    quotation = Quotation(
        number=service.create_quotation_number(db),
        customer_id=payload.customer_id,
        plan_id=payload.plan_id or (template.plan_id if template else None),
        template_id=payload.template_id,
        created_by=user.id,
        payment_terms=payload.payment_terms or (template.payment_terms if template else None),
        start_date=payload.start_date,
        notes=payload.notes,
        status="draft",
        valid_until=None,  # starts counting on send
    )
    db.add(quotation)
    db.flush()
    service.replace_lines(db, quotation, resolved)
    db.commit()
    db.refresh(quotation)
    return quotation


@router.get("/quotations/{quotation_id}", response_model=QuotationOut)
def get_quotation(
    quotation_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    quotation = _quotation_visible(db, quotation_id, user)
    return _serialize(quotation)


def _serialize(quotation: Quotation) -> QuotationOut:
    """Serialize with lazy expiry applied — reads as 'expired' without a DB write."""
    out = QuotationOut.model_validate(quotation)
    eff = service.effective_status(quotation)
    if eff != out.status:
        out.status = eff
    return out


@router.patch("/quotations/{quotation_id}", response_model=QuotationOut)
def patch_quotation(
    quotation_id: int,
    payload: QuotationPatchIn,
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    quotation = _quotation_visible(db, quotation_id, user)
    if quotation.status not in ("draft", "sent"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot edit a {quotation.status} quotation")

    data = payload.model_dump(exclude_unset=True)
    lines_payload = data.pop("lines", None)
    if payload.plan_id is not None:
        from app.catalog.models import Plan

        if db.get(Plan, payload.plan_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "plan_id not found")

    for key, value in data.items():
        if key == "validity_days":
            if quotation.status == "sent" and quotation.valid_until:
                from datetime import timedelta

                quotation.valid_until = service.today() + timedelta(days=value)
            continue
        setattr(quotation, key, value)

    if lines_payload is not None:
        resolved = service.resolve_lines(db, [QuotationLineIn(**l) for l in lines_payload])
        service.replace_lines(db, quotation, resolved)

    db.commit()
    db.refresh(quotation)
    return _serialize(quotation)


@router.post("/quotations/{quotation_id}/send", response_model=QuotationOut)
def send_quotation(
    quotation_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    quotation = _quotation_visible(db, quotation_id, user)
    return _serialize(service.send_quotation(db, quotation))


@router.post("/quotations/{quotation_id}/confirm", response_model=ConfirmOut, status_code=status.HTTP_201_CREATED)
def confirm_quotation(
    quotation_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Convert quotation → subscription (customer accepts, or staff confirms)."""
    from app.subscriptions.service import convert_quotation  # local: subscriptions imports quoting

    quotation = _quotation_visible(db, quotation_id, user)
    if user.role == "customer" and quotation.status != "sent":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a sent quotation can be accepted")
    service.ensure_convertible(quotation)
    subscription = convert_quotation(db, quotation, user)  # single transaction, exactly once
    return {"quotation": _serialize(quotation), "subscription": subscription}


@router.post("/quotations/{quotation_id}/cancel", response_model=QuotationOut)
def cancel_quotation(
    quotation_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    quotation = _quotation_visible(db, quotation_id, user)
    if quotation.status not in ("draft", "sent"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot cancel a {quotation.status} quotation")
    quotation.status = "cancelled"
    db.commit()
    db.refresh(quotation)
    return quotation


@router.get("/quotations/{quotation_id}/pdf")
def quotation_pdf(
    quotation_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _quotation_visible(db, quotation_id, user)
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "PDF generation lands in the invoice/PDF block")
