"""The catalogue, the cross-reference table and the matching sandbox."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..domain.partnumbers import parse_specification
from ..models import Contract, ContractLine, CrossReference, Customer, Product, StockLevel, User
from ..security import get_current_user
from ..serializers import product_out
from ..services import matching

router = APIRouter(prefix="/api/catalogue", tags=["Catalogue"])


@router.get("/products")
def search_products(
    query: str = "",
    family: str | None = None,
    limit: int = 25,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    statement = select(Product).where(Product.is_active.is_(True))
    if family:
        statement = statement.where(Product.family == family)
    if query:
        pattern = f"%{query.lower()}%"
        statement = statement.where(
            or_(
                func.lower(Product.sku).like(pattern),
                func.lower(Product.description_en).like(pattern),
                func.lower(Product.search_text).like(pattern),
            )
        )
    products = list(session.scalars(statement.order_by(Product.sku).limit(min(limit, 100))))
    total = int(
        session.scalar(select(func.count()).select_from(Product).where(Product.is_active.is_(True)))
        or 0
    )
    return {
        "total_in_catalogue": total,
        "returned": len(products),
        "products": [product_out(p) for p in products],
    }


@router.get("/products/{product_id}")
def get_product(
    product_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="No such part.")

    stock = [
        {
            "warehouse": level.warehouse_code,
            "on_hand": level.quantity_on_hand,
            "allocated": level.quantity_allocated,
            "available": level.available,
        }
        for level in session.scalars(select(StockLevel).where(StockLevel.product_id == product.id))
    ]
    references = [
        {
            "brand": reference.brand,
            "number": reference.external_number,
            "equivalence": reference.equivalence,
            "note": reference.note,
            "verified_by": reference.verified_by,
        }
        for reference in session.scalars(
            select(CrossReference).where(CrossReference.product_id == product.id)
        )
    ]
    contracts = [
        {
            "contract": contract.code,
            "customer": customer.name,
            "unit_price": str(line.unit_price),
            "valid_from": contract.valid_from.isoformat(),
            "valid_to": contract.valid_to.isoformat(),
        }
        for line, contract, customer in session.execute(
            select(ContractLine, Contract, Customer)
            .join(Contract, ContractLine.contract_id == Contract.id)
            .join(Customer, Contract.customer_id == Customer.id)
            .where(ContractLine.product_id == product.id)
            .limit(20)
        ).all()
    ]
    breaks = [
        {"price_tier": b.price_tier, "minimum_quantity": b.minimum_quantity,
         "unit_price": str(b.unit_price)}
        for b in sorted(product.price_breaks, key=lambda b: (b.price_tier, b.minimum_quantity))
    ]
    return {
        "product": product_out(product),
        "stock": stock,
        "cross_references": references,
        "contracts": contracts,
        "volume_prices": breaks,
    }


class MatchProbe(BaseModel):
    text: str


@router.post("/match")
def try_matching(
    payload: MatchProbe,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Type anything a customer might write and see exactly how it is handled.

    This is the screen that answers "but what would it do with ...", which is
    the question every engineer in the room asks.
    """
    specification = parse_specification(payload.text)
    result = matching.match_line(session, payload.text, specification=specification)
    payload_out = result.to_dict()
    payload_out["how_it_was_read"] = {
        "family": specification.family,
        "standard": specification.standard,
        "attributes": specification.attributes,
        "missing": specification.missing,
        "conflicts": specification.conflicts,
        "notes": specification.notes,
    }
    if result.product is not None:
        payload_out["product"] = product_out(result.product)
    return payload_out


@router.get("/summary")
def summary(
    session: Session = Depends(get_session), _user: User = Depends(get_current_user)
) -> dict[str, Any]:
    families = session.execute(
        select(Product.family, func.count()).group_by(Product.family)
    ).all()
    stocked = int(
        session.scalar(
            select(func.count()).select_from(Product).where(Product.is_stocked.is_(True))
        )
        or 0
    )
    references = int(session.scalar(select(func.count()).select_from(CrossReference)) or 0)
    return {
        "families": [{"family": family, "count": count} for family, count in families],
        "stocked": stocked,
        "cross_references": references,
        "explanation": (
            "The cross-reference table is what turns a competitor part number or a "
            "published standard into a part Hengtai can sell. Every proposal from it "
            "is still checked attribute by attribute before it becomes a match."
        ),
    }
