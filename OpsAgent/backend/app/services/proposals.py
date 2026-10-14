"""Things worth doing, written down and left for a person.

This is the part of the product that is a deliberate absence.

An operations agent that can read the whole business and also act on it
is two products, and the second one is the one that gets switched off
after the first bad week. So this system proposes and stops. A proposal
records what was noticed, which answer it came from, and which role is
allowed to decide. Deciding it marks it approved or declined, with a
name and a time against it, and that is the end of the code path —
there is no executor, no queue and no integration behind ``approve``.

If somebody later wants the system to act, the honest way to build it is
to write a separate service that reads approved proposals, and to make
that service's permissions a separate conversation. Bolting a write onto
this module would make every reassurance in this repository untrue.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Proposal, Question, User
from ..security import ROLE_LABELS, role_satisfies


class CannotDecide(Exception):
    """The wrong person, or an already-decided proposal."""


def _next_reference(session: Session) -> str:
    count = session.scalar(select(func.count(Proposal.id))) or 0
    return f"P-{4000 + count + 1}"


def raise_from_answer(
    session: Session, question: Question, suggestions: list[dict[str, Any]]
) -> list[Proposal]:
    """Write down what the answer suggested. Nothing is done about it."""
    out: list[Proposal] = []
    for suggestion in suggestions:
        proposal = Proposal(
            reference=_next_reference(session),
            question_id=question.id,
            kind=suggestion["kind"],
            summary=suggestion["summary"],
            detail=suggestion.get("detail", {}),
            needs_role=suggestion.get("needs_role", "manager"),
            status="proposed",
        )
        session.add(proposal)
        session.flush()
        out.append(proposal)
    return out


def decide(
    session: Session,
    proposal: Proposal,
    user: User,
    *,
    approve: bool,
    note: str = "",
) -> Proposal:
    """A person decides. The system records the decision and does nothing.

    The role check is the same one the rest of the product uses, and it
    fails closed, so a proposal whose ``needs_role`` was mistyped is
    decidable by nobody rather than by everybody.
    """
    if proposal.status != "proposed":
        raise CannotDecide(
            f"{proposal.reference} was already "
            f"{proposal.status} by "
            f"{proposal.decided_by.full_name if proposal.decided_by else 'somebody'}."
        )
    if not role_satisfies(user.role, proposal.needs_role):
        raise CannotDecide(
            f"{proposal.reference} needs the "
            f"{ROLE_LABELS.get(proposal.needs_role, proposal.needs_role)} role, "
            f"and you are signed in as "
            f"{ROLE_LABELS.get(user.role, user.role)}."
        )

    proposal.status = "approved" if approve else "declined"
    proposal.decided_by_id = user.id
    proposal.decided_at = dt.datetime.now(dt.timezone.utc)
    proposal.note = note.strip()[:2000]
    session.flush()
    # And that is all. Approving does not place an order, send an email
    # or write to any other table. See the note at the top of this file.
    return proposal
