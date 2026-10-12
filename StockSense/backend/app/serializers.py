"""Database rows into the shapes the screens draw.

Money leaves here as a string. Quantities leave as numbers, because they
are counts and a count is not a price.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .domain import calendar as shutdowns, classify, forecast as models, leadtime as leadtimes
from .models import Part, PlanLine, PlanRun, Supplier, User
from .numbers import dec, money
from .security import ROLE_LABELS
from .services.reorder import DECISION_LABELS, REASON_LABELS


def when(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None


def day(value: dt.date | None) -> str | None:
    return value.isoformat() if value else None


def user_brief(user: User | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "name": user.full_name,
        "email": user.email,
        "role": user.role,
        "role_label": ROLE_LABELS.get(user.role, user.role),
    }


def user_detail(user: User) -> dict[str, Any]:
    out = user_brief(user) or {}
    out["is_active"] = user.is_active
    return out


def supplier_brief(supplier: Supplier | None) -> dict[str, Any] | None:
    if supplier is None:
        return None
    profile = leadtimes.profile(
        supplier.quoted_lead_time_days, supplier.lead_time_samples or []
    )
    return {
        "id": supplier.id,
        "code": supplier.code,
        "name": supplier.name,
        "country": supplier.country,
        "currency": supplier.currency,
        "lead_time": profile.to_dict(),
    }


def supplier_detail(session: Session, supplier: Supplier, today: dt.date) -> dict[str, Any]:
    out = supplier_brief(supplier) or {}
    shutdown = shutdowns.next_shutdown(supplier.country, today)
    parts = session.scalar(
        select(func.count(Part.id)).where(Part.supplier_id == supplier.id)
    )
    out.update(
        {
            "minimum_order_value": str(money(supplier.minimum_order_value)),
            "container_cubic_metres": str(money(supplier.container_cubic_metres)),
            "parts": parts or 0,
            "shutdown": shutdown.to_dict() if shutdown else None,
            "weeks_of_cover_needed": round(
                shutdowns.weeks_of_cover_needed(shutdown), 1
            ),
            "days_until_order_by": (
                shutdown.days_until_order_by(today) if shutdown else None
            ),
            "lead_time_samples": list(supplier.lead_time_samples or []),
        }
    )
    return out


def part_brief(part: Part) -> dict[str, Any]:
    return {
        "id": part.id,
        "code": part.code,
        "description": part.description,
        "family": part.family.replace("_", " "),
        "abc_class": part.abc_class,
        "unit_cost": str(money(part.unit_cost)),
        "pack_size": part.pack_size,
        "minimum_order_quantity": part.minimum_order_quantity,
        "on_hand": part.on_hand,
        "on_order": part.on_order,
        "on_order_due": day(part.on_order_due),
        "is_active": part.is_active,
        "replaced_by_part_id": part.replaced_by_part_id,
        "replaces_part_id": part.replaces_part_id,
        "supplier": supplier_brief(part.supplier),
        "stock_value": str(money(dec(part.on_hand) * part.unit_cost)),
    }


def plan_line(line: PlanLine, *, with_trace: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": line.id,
        "part": part_brief(line.part),
        "decision": line.decision,
        "decision_label": DECISION_LABELS.get(line.decision, line.decision),
        "reason": line.reason,
        "reason_label": REASON_LABELS.get(line.reason, line.reason),
        "quantity": line.quantity,
        "value": str(money(line.value)),
        "demand_method": line.demand_method,
        "demand_method_label": models.METHOD_LABELS.get(
            line.demand_method, line.demand_method
        ),
        "demand_pattern": line.demand_pattern,
        "demand_pattern_label": classify.LABELS.get(
            line.demand_pattern, line.demand_pattern
        ),
        "weekly_rate": str(money(line.weekly_rate)),
        "reorder_point": str(money(line.reorder_point)),
        "order_up_to": str(money(line.order_up_to)),
        "safety_stock": str(money(line.safety_stock)),
        "position": str(money(line.position)),
        "lead_time_days": str(money(line.lead_time_days)),
        "service_level": float(dec(line.service_level)),
        "days_of_cover": float(dec(line.days_of_cover)),
        "urgency": float(dec(line.urgency)),
        "shutdown_note": line.shutdown_note,
        "flags": line.flags or [],
    }
    if with_trace:
        out["trace"] = line.trace or None
    return out


def plan_run(run: PlanRun, *, lines: list[PlanLine] | None = None) -> dict[str, Any]:
    return {
        "id": run.id,
        "as_of": day(run.as_of),
        "created_at": when(run.created_at),
        "created_by": user_brief(run.created_by),
        "cash_cap": str(money(run.cash_cap)),
        "cash_committed": str(money(run.cash_committed)),
        "cash_remaining": str(money(dec(run.cash_cap) - dec(run.cash_committed))),
        "parts_considered": run.parts_considered,
        "lines_recommended": run.lines_recommended,
        "lines_deferred": run.lines_deferred,
        "seconds": float(dec(run.seconds)),
        "notes": run.notes,
        "lines": [plan_line(line) for line in (lines or [])],
    }


def plan_summary(session: Session, run: PlanRun) -> dict[str, Any]:
    """The counts the front page needs, without loading every line."""
    rows = session.execute(
        select(PlanLine.decision, PlanLine.reason, func.count(PlanLine.id))
        .where(PlanLine.run_id == run.id)
        .group_by(PlanLine.decision, PlanLine.reason)
    )
    by_decision: dict[str, int] = {}
    by_reason: list[dict[str, Any]] = []
    for decision, reason, number in rows:
        by_decision[decision] = by_decision.get(decision, 0) + number
        by_reason.append(
            {
                "decision": decision,
                "reason": reason,
                "label": REASON_LABELS.get(reason, reason),
                "count": number,
            }
        )
    by_reason.sort(key=lambda row: -row["count"])

    patterns = session.execute(
        select(PlanLine.demand_pattern, func.count(PlanLine.id))
        .where(PlanLine.run_id == run.id)
        .group_by(PlanLine.demand_pattern)
    )
    return {
        **plan_run(run),
        "by_decision": [
            {
                "decision": decision,
                "label": DECISION_LABELS.get(decision, decision),
                "count": number,
            }
            for decision, number in sorted(by_decision.items(), key=lambda kv: -kv[1])
        ],
        "by_reason": by_reason,
        "by_pattern": [
            {
                "pattern": pattern,
                "label": classify.LABELS.get(pattern, pattern),
                "count": number,
            }
            for pattern, number in sorted(patterns, key=lambda kv: -kv[1])
        ],
    }


def dashboard(session: Session, today: dt.date) -> dict[str, Any]:
    """Every figure here is one query, so the page cannot disagree with itself."""
    parts = session.scalar(select(func.count(Part.id))) or 0
    suppliers = session.scalar(select(func.count(Supplier.id))) or 0

    stock_value = sum(
        (dec(on_hand) * dec(cost) for on_hand, cost in session.execute(
            select(Part.on_hand, Part.unit_cost)
        )),
        dec(0),
    )

    latest = session.scalar(select(PlanRun).order_by(PlanRun.id.desc()).limit(1))

    # Shutdowns a buyer has to act on soon, by supplier country.
    upcoming: list[dict[str, Any]] = []
    for country, in session.execute(select(Supplier.country).distinct()):
        shutdown = shutdowns.next_shutdown(country, today)
        if shutdown is None or not shutdown.affects:
            continue
        affected = session.scalar(
            select(func.count(Part.id))
            .join(Supplier, Part.supplier_id == Supplier.id)
            .where(Supplier.country == country)
        )
        upcoming.append(
            {
                **shutdown.to_dict(),
                "days_until_order_by": shutdown.days_until_order_by(today),
                "weeks_of_cover_needed": round(
                    shutdowns.weeks_of_cover_needed(shutdown), 1
                ),
                "parts": affected or 0,
            }
        )
    upcoming.sort(key=lambda row: row["days_until_order_by"])

    return {
        "parts": parts,
        "suppliers": suppliers,
        "stock_value": str(money(stock_value)),
        "carrying_cost_low": str(
            money(stock_value * dec(settings.carrying_cost_percent_low) / 100)
        ),
        "carrying_cost_high": str(
            money(stock_value * dec(settings.carrying_cost_percent_high) / 100)
        ),
        "weekly_cash_cap": str(money(settings.weekly_cash_cap_twd)),
        "latest_plan": plan_run(latest) if latest else None,
        "shutdowns": upcoming,
    }
