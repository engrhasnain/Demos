"""A handful of asked questions, seeded once, so a fresh deployment opens
with every screen meaningful rather than empty.

Used only by :mod:`app.bootstrap`, after the generated business data is in
place. Nothing here is invented: each line below calls the real
``services.answering.ask`` with a real signed-in account, so what lands in
the question log, the access record and the proposal tray is exactly what
a person asking those questions would have produced. The point is screens
with something on them on the first open, not a shortcut around the
engine.

Chosen to cover the product's own claims: an ordinary answer, a whole-
company figure open to a director, the same figure refused to a
salesperson, a proposal raised for a person to decide, and the planted
document read alongside a question so the "fooled planner reaches
nothing extra" case has something to point at before anybody has typed a
word.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Document, User
from ..services import answering, proposals as proposal_service

log = logging.getLogger("opsagent")

#: (email, question, document reference or "") in the order they are asked.
EXAMPLE_QUESTIONS: list[tuple[str, str, str]] = [
    ("clare.whitfield@hengtai-industrial.example", "How are we doing this week?", ""),
    ("clare.whitfield@hengtai-industrial.example", "Which customers have late orders?", ""),
    ("clare.whitfield@hengtai-industrial.example", "What is owed altogether?", ""),
    (
        "clare.whitfield@hengtai-industrial.example",
        "What happens if \"Chang Hsing Fastener (TW)\" shuts down?",
        "",
    ),
    # Refused: the same whole-company question, asked by somebody with
    # four accounts rather than every account.
    ("jun.wei@hengtai-industrial.example", "What is owed altogether?", ""),
    ("jun.wei@hengtai-industrial.example", "Which customers have late orders?", ""),
    # The fooled-planner example: an ordinary question asked alongside the
    # planted supplier email that tries to give the system instructions.
    # The plan the question alone produces is the plan that runs; the
    # instructions are read as text and go nowhere.
    ("clare.whitfield@hengtai-industrial.example", "What is owed altogether?", "E-9001"),
]


def ask_example_questions(session: Session) -> int:
    """Run the questions above for real. Returns how many were asked."""
    users = {
        user.email: user
        for user in session.scalars(select(User)).all()
    }
    documents = {
        document.reference: document
        for document in session.scalars(select(Document)).all()
    }

    asked = 0
    for email, question, document_reference in EXAMPLE_QUESTIONS:
        user = users.get(email)
        if user is None:
            continue
        content = ""
        if document_reference:
            document = documents.get(document_reference)
            if document is not None:
                content = f"{document.subject}\n\n{document.body}"
        try:
            answer = answering.ask(session, user, question, content=content)
        except Exception:  # pragma: no cover - a seed question must never
            # block the deployment from opening with the business data it
            # already has.
            log.exception("Seeding the example question %r failed.", question)
            continue
        asked += 1
        if answer.ok and answer.proposals and answer.question_id:
            from ..models import Question

            logged_question = session.get(Question, answer.question_id)
            if logged_question is not None:
                proposal_service.raise_from_answer(session, logged_question, answer.proposals)
    return asked
