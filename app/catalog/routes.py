"""Catalog endpoints. Reads: staff+. Writes: admin only (discount rules: admin only, full stop)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.catalog.models import DiscountRule, Plan, Product, ProductVariant, TaxRule
from app.catalog.schemas import (
    DiscountRuleCreateIn,
    DiscountRuleOut,
    DiscountRulePatchIn,
    PlanCreateIn,
    PlanOut,
    PlanPatchIn,
    ProductCreateIn,
    ProductOut,
    ProductPatchIn,
    TaxRuleCreateIn,
    TaxRuleOut,
    TaxRulePatchIn,
    VariantCreateIn,
    VariantOut,
    VariantPatchIn,
)
from app.core.database import get_db
from app.core.dependencies import require_admin, require_staff
from app.core.pagination import paginate

router = APIRouter(prefix="/api/v1", tags=["catalog"])


def _get_or_404(db: Session, model, obj_id: int, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found")
    return obj


# ------------------------------------------------------------------ products
@router.get("/products")
def list_products(
    q: str | None = Query(None, min_length=1),
    is_active: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: object = Depends(require_staff),
):
    stmt = select(Product)
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q}%"))
    if is_active is not None:
        stmt = stmt.where(Product.is_active.is_(is_active))
    return paginate(db, stmt.order_by(Product.id), page, page_size)


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreateIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_staff),
):
    return _get_or_404(db, Product, product_id, "Product")


@router.patch("/products/{product_id}", response_model=ProductOut)
def patch_product(
    product_id: int,
    payload: ProductPatchIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    product = _get_or_404(db, Product, product_id, "Product")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return product


# ----------------------------------------------------------------- variants
@router.get("/products/{product_id}/variants", response_model=list[VariantOut])
def list_variants(
    product_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_staff),
):
    _get_or_404(db, Product, product_id, "Product")
    return db.scalars(
        select(ProductVariant).where(ProductVariant.product_id == product_id).order_by(ProductVariant.id)
    ).all()


@router.post(
    "/products/{product_id}/variants", response_model=VariantOut, status_code=status.HTTP_201_CREATED
)
def create_variant(
    product_id: int,
    payload: VariantCreateIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    _get_or_404(db, Product, product_id, "Product")
    exists = db.scalar(
        select(ProductVariant).where(
            ProductVariant.product_id == product_id,
            ProductVariant.attribute == payload.attribute,
            ProductVariant.value == payload.value,
        )
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "This variant already exists on the product")
    variant = ProductVariant(product_id=product_id, **payload.model_dump())
    db.add(variant)
    db.commit()
    db.refresh(variant)
    return variant


@router.patch("/variants/{variant_id}", response_model=VariantOut)
def patch_variant(
    variant_id: int,
    payload: VariantPatchIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    variant = _get_or_404(db, ProductVariant, variant_id, "Variant")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(variant, key, value)
    db.commit()
    db.refresh(variant)
    return variant


@router.delete("/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_variant(
    variant_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    variant = _get_or_404(db, ProductVariant, variant_id, "Variant")
    db.delete(variant)
    db.commit()


# --------------------------------------------------------------------- plans
@router.get("/plans")
def list_plans(
    q: str | None = Query(None, min_length=1),
    plan_status: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: object = Depends(require_staff),
):
    stmt = select(Plan)
    if q:
        stmt = stmt.where(Plan.name.ilike(f"%{q}%"))
    if plan_status:
        stmt = stmt.where(Plan.status == plan_status)
    return paginate(db, stmt.order_by(Plan.id), page, page_size)


@router.post("/plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: PlanCreateIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    plan = Plan(**payload.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/plans/{plan_id}", response_model=PlanOut)
def get_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_staff),
):
    return _get_or_404(db, Plan, plan_id, "Plan")


@router.patch("/plans/{plan_id}", response_model=PlanOut)
def patch_plan(
    plan_id: int,
    payload: PlanPatchIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    plan = _get_or_404(db, Plan, plan_id, "Plan")
    data = payload.model_dump(exclude_unset=True)
    # If dates are being changed, validate the resulting combination
    new_from = data.get("available_from", plan.available_from)
    new_to = data.get("available_to", plan.available_to)
    if new_from and new_to and new_from > new_to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "available_from must be on or before available_to")
    for key, value in data.items():
        setattr(plan, key, value)
    db.commit()
    db.refresh(plan)
    return plan


@router.post("/plans/{plan_id}/close", response_model=PlanOut)
def close_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    plan = _get_or_404(db, Plan, plan_id, "Plan")
    plan.status = "closed"
    db.commit()
    db.refresh(plan)
    return plan


@router.post("/plans/{plan_id}/reopen", response_model=PlanOut)
def reopen_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    plan = _get_or_404(db, Plan, plan_id, "Plan")
    plan.status = "active"
    db.commit()
    db.refresh(plan)
    return plan


# --------------------------------------------------------------- tax rules
@router.get("/tax-rules", response_model=list[TaxRuleOut])
def list_tax_rules(
    db: Session = Depends(get_db),
    _: object = Depends(require_staff),
):
    return db.scalars(select(TaxRule).order_by(TaxRule.priority, TaxRule.id)).all()


@router.post("/tax-rules", response_model=TaxRuleOut, status_code=status.HTTP_201_CREATED)
def create_tax_rule(
    payload: TaxRuleCreateIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    if payload.product_id is not None:
        _get_or_404(db, Product, payload.product_id, "Product")
    rule = TaxRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/tax-rules/{rule_id}", response_model=TaxRuleOut)
def patch_tax_rule(
    rule_id: int,
    payload: TaxRulePatchIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    rule = _get_or_404(db, TaxRule, rule_id, "Tax rule")
    data = payload.model_dump(exclude_unset=True)
    if data.get("product_id") is not None:
        _get_or_404(db, Product, data["product_id"], "Product")
    for key, value in data.items():
        setattr(rule, key, value)
    db.commit()
    db.refresh(rule)
    return rule


# ---------------------------------------------------------- discount rules (ADMIN ONLY)
@router.get("/discount-rules", response_model=list[DiscountRuleOut])
def list_discount_rules(
    db: Session = Depends(get_db),
    _: object = Depends(require_staff),
):
    return db.scalars(select(DiscountRule).order_by(DiscountRule.id)).all()


@router.get("/discount-rules/{rule_id}", response_model=DiscountRuleOut)
def get_discount_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_staff),
):
    return _get_or_404(db, DiscountRule, rule_id, "Discount rule")


@router.post("/discount-rules", response_model=DiscountRuleOut, status_code=status.HTTP_201_CREATED)
def create_discount_rule(
    payload: DiscountRuleCreateIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    """Only the admin can create discount rules (problem statement)."""
    if payload.product_id is not None:
        _get_or_404(db, Product, payload.product_id, "Product")
    rule = DiscountRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/discount-rules/{rule_id}", response_model=DiscountRuleOut)
def patch_discount_rule(
    rule_id: int,
    payload: DiscountRulePatchIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    rule = _get_or_404(db, DiscountRule, rule_id, "Discount rule")
    data = payload.model_dump(exclude_unset=True)
    new_type = rule.type
    new_value = data.get("value", rule.value)
    if new_type == "percentage" and new_value > 100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "percentage discount cannot exceed 100")
    new_start = data.get("starts_at", rule.starts_at)
    new_end = data.get("ends_at", rule.ends_at)
    if new_end and new_end < new_start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "ends_at must be on or after starts_at")
    for key, value in data.items():
        setattr(rule, key, value)
    db.commit()
    db.refresh(rule)
    return rule


_ = or_  # keep import intent explicit for future filters
