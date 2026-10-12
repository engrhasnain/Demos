"""Duty tables, exchange rates and freight: the numbers a person owns.

Activating a newer duty table is the moment that proves the design. Every open
quote priced on an older version is flagged for re-pricing, by name, with the
reason recorded on each case timeline.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Case, ExchangeRate, FreightRate, QuoteVersion, TariffTable, User
from ..security import get_current_user, require_role
from ..serializers import tariff_table_out
from ..services.audit import record_change, record_event
from ..services.casestate import TERMINAL

router = APIRouter(prefix="/api/rates", tags=["Duty, currency and freight"])


@router.get("/tariff-tables")
def list_tables(
    session: Session = Depends(get_session), _user: User = Depends(get_current_user)
) -> dict[str, Any]:
    tables = list(
        session.scalars(select(TariffTable).order_by(TariffTable.effective_from.desc()))
    )
    return {
        "tables": [tariff_table_out(t) for t in tables],
        "principle": (
            "Duty is never worked out by the reasoning engine and never written into "
            "the code. It is read from the one table that was active on the quote "
            "date. Every quote records which version priced it. Confirm current duty "
            "with a licensed customs broker before shipment."
        ),
    }


@router.get("/tariff-tables/{table_id}")
def get_table(
    table_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    table = session.get(TariffTable, table_id)
    if table is None:
        raise HTTPException(status_code=404, detail="No such duty table.")
    return tariff_table_out(table, include_lines=True)


class ActivateRequest(BaseModel):
    confirm_broker_sign_off: bool = False
    customs_broker: str = ""


@router.post("/tariff-tables/{table_id}/activate")
def activate_table(
    table_id: int,
    payload: ActivateRequest,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("pricing_owner")),
) -> dict[str, Any]:
    table = session.get(TariffTable, table_id)
    if table is None:
        raise HTTPException(status_code=404, detail="No such duty table.")
    if table.status == "active":
        raise HTTPException(status_code=409, detail="That duty table is already the active one.")
    if table.effective_from > dt.date.today():
        # Without this, superseding the current table would leave no table in
        # force at all and every quote needing duty would fail to price.
        raise HTTPException(
            status_code=409,
            detail=(
                f"{table.version} starts {table.effective_from.isoformat()}. "
                "Activating it now would leave no table in force."
            ),
        )
    if not table.lines:
        raise HTTPException(
            status_code=409,
            detail=f"Duty table {table.version} has no rates in it.",
        )

    if payload.confirm_broker_sign_off:
        table.customs_broker = payload.customs_broker or table.customs_broker or user.full_name
        table.broker_signed_off_at = dt.datetime.now(dt.timezone.utc)

    previous = list(session.scalars(select(TariffTable).where(TariffTable.status == "active")))
    for old in previous:
        old.status = "superseded"
        old.effective_to = table.effective_from
    table.status = "active"
    session.flush()

    # Flag every open quote priced on an older table.
    flagged: list[dict[str, Any]] = []
    for case in session.scalars(select(Case).where(Case.status.notin_(tuple(TERMINAL)))):
        for version in case.quote_versions:
            if version.status == "superseded":
                continue
            if version.tariff_table_id in (None, table.id):
                continue
            version.needs_repricing = True
            version.repricing_reason = (
                f"Priced on {version.tariff_table.version if version.tariff_table else 'unknown'}, "
                f"{table.version} is now in force"
            )
            flagged.append(
                {
                    "case_id": case.id,
                    "reference": case.reference,
                    "version": version.version_number,
                    "priced_on": version.tariff_table.version if version.tariff_table else "",
                    "grand_total": str(version.grand_total),
                    "currency": version.currency,
                }
            )
            record_event(
                session,
                case_id=case.id,
                kind="repricing_required",
                summary=(
                    f"Duty table {table.version} came into force, so quote version "
                    f"{version.version_number} has to be re-priced."
                ),
                actor_type="system",
                actor_name="Duty table",
                detail={"new_table": table.version, "old_table": version.repricing_reason},
            )

    record_change(
        session, user=user, action="activate", entity="tariff_table", entity_id=table.id,
        before={"status": "draft"},
        after={"status": "active", "signed_off": table.is_signed_off, "flagged": len(flagged)},
    )
    return {
        "activated": tariff_table_out(table),
        "quotes_flagged_for_repricing": flagged,
        "warning": (
            ""
            if table.is_signed_off
            else "This table has not been signed off by a customs broker. Quotes priced "
            "on it will carry a provisional duty warning and need a pricing owner "
            "approval before they are sent."
        ),
    }


@router.get("/exchange-rates")
def exchange_rates(
    base: str = "TWD",
    quote: str = "USD",
    limit: int = 20,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    rows = list(
        session.scalars(
            select(ExchangeRate)
            .where(ExchangeRate.base_currency == base, ExchangeRate.quote_currency == quote)
            .order_by(ExchangeRate.as_of_date.desc())
            .limit(min(limit, 100))
        )
    )
    return {
        "pair": f"{base} to {quote}",
        "rates": [
            {
                "id": row.id,
                "rate": str(row.rate),
                "as_of_date": row.as_of_date.isoformat(),
                "source": row.source,
            }
            for row in rows
        ],
        "note": (
            "A quote locks the rate published on its quote date and holds it for the "
            "validity period printed on the quote."
        ),
    }


@router.get("/freight")
def freight(
    session: Session = Depends(get_session), _user: User = Depends(get_current_user)
) -> dict[str, Any]:
    rows = list(session.scalars(select(FreightRate)))
    return {
        "rates": [
            {
                "id": row.id,
                "lane": f"{row.origin_country} to {row.destination_country}",
                "mode": row.mode,
                "minimum_charge": str(row.minimum_charge),
                "price_per_kilogram": str(row.price_per_kilogram),
                "handling_per_shipment": str(row.handling_per_shipment),
                "insurance_percent": str(row.insurance_percent),
                "transit_days": row.transit_days,
                "currency": row.currency,
            }
            for row in rows
        ],
        "note": (
            "Freight is a table the logistics team owns. Whether it is charged to the "
            "customer at all is decided by the Incoterms 2020 rule on the quote."
        ),
    }


@router.get("/quotes-needing-repricing")
def quotes_needing_repricing(
    session: Session = Depends(get_session), _user: User = Depends(get_current_user)
) -> dict[str, Any]:
    versions = list(
        session.scalars(select(QuoteVersion).where(QuoteVersion.needs_repricing.is_(True)))
    )
    return {
        "count": len(versions),
        "quotes": [
            {
                "case_id": version.case_id,
                "reference": version.case.reference,
                "version": version.version_number,
                "reason": version.repricing_reason,
                "grand_total": str(version.grand_total),
                "currency": version.currency,
            }
            for version in versions
        ],
    }
