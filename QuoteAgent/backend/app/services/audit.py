"""Writing down what happened.

Two separate records, on purpose:

* the **case timeline** is the story of the quote, shown to the salesperson and
  to the client in the demonstration, including what each step cost;
* the **audit trail** is who changed what, which is what a controller asks for.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditEntry, CaseEvent, User


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
    case_id: int,
    kind: str,
    summary: str,
    actor_type: str = "agent",
    actor_name: str = "QuoteAgent",
    detail: dict[str, Any] | None = None,
    duration_ms: int = 0,
    engine: str = "",
    model: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: Decimal | float | str = 0,
) -> CaseEvent:
    event = CaseEvent(
        case_id=case_id,
        kind=kind,
        summary=summary[:400],
        actor_type=actor_type,
        actor_name=actor_name,
        detail=_clean(detail or {}),
        duration_ms=duration_ms,
        engine=engine,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
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
