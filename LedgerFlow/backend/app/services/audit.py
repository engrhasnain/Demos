"""Writing down what happened.

Two separate records, on purpose:

* the **invoice timeline** is the story of one invoice, step by step,
  including what each step cost;
* the **audit trail** is who changed what, which is what a controller asks for.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditEntry, InvoiceEvent, User


def _clean(value: Any) -> Any:
    """Make a value safe to store as JSON."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


def record_event(
    session: Session,
    *,
    invoice_id: int,
    kind: str,
    summary: str,
    actor_type: str = "agent",
    actor_name: str = "LedgerFlow",
    detail: dict[str, Any] | None = None,
    duration_ms: int = 0,
    engine: str = "",
    cost_usd: Decimal | float | str = 0,
) -> InvoiceEvent:
    event = InvoiceEvent(
        invoice_id=invoice_id,
        kind=kind,
        summary=summary[:400],
        actor_type=actor_type,
        actor_name=actor_name,
        detail=_clean(detail or {}),
        duration_ms=duration_ms,
        engine=engine,
        cost_usd=Decimal(str(cost_usd)),
    )
    session.add(event)
    session.flush()
    return event


def record_change(
    session: Session,
    *,
    user: User | None,
    action: str,
    entity: str,
    entity_id: Any,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditEntry:
    entry = AuditEntry(
        user_id=user.id if user else None,
        user_email=user.email if user else "system",
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        before=_clean(before or {}),
        after=_clean(after or {}),
    )
    session.add(entry)
    session.flush()
    return entry
