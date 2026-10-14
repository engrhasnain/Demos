"""Running a capability, and keeping the receipt.

Every figure this system shows comes back from here with three things
attached: the SQL that produced it, the parameters it ran with, and the
moment it was read. Not in a log somewhere — on the number, in the
response, on the screen.

That is what "traceable" has to mean to be worth anything. "The system
says forty-one" is not an answer a chief operating officer can act on.
"Forty-one, from this query, run at 09:14, over these accounts" is.

Parameters are bound, never formatted. A parameter is also validated
against the kind the capability declared before it gets near the
database, so a customer parameter that is not an integer is a refusal
rather than a string in a query.
"""

from __future__ import annotations

import datetime as dt
import re
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..domain.capabilities import Capability, Parameter
from .permissions import NotAllowed, Reach, apply, may_use


class BadParameter(Exception):
    pass


_TEXT_OK = re.compile(r"^[A-Za-z0-9 ._\-/()&',]{1,80}$")


def _check(parameter: Parameter, value: Any) -> Any:
    """Make the value the kind the capability asked for, or refuse."""
    if value is None or value == "":
        if parameter.required:
            raise BadParameter(f"{parameter.name} is needed and was not given.")
        return None

    kind = parameter.kind
    if kind in {"customer", "supplier", "number", "days"}:
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise BadParameter(
                f"{parameter.name} has to be a number, and {value!r} is not."
            ) from error

    if kind == "date":
        try:
            return dt.date.fromisoformat(str(value)).isoformat()
        except ValueError as error:
            raise BadParameter(
                f"{parameter.name} has to be a date, and {value!r} is not."
            ) from error

    if kind == "part":
        cleaned = str(value).strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{1,47}", cleaned):
            raise BadParameter(f"{value!r} is not a part code.")
        return cleaned

    # Plain text, for a name search. Kept narrow, and bound rather than
    # formatted, so the shape of it is belt as well as braces.
    cleaned = str(value).strip()
    if not _TEXT_OK.fullmatch(cleaned):
        raise BadParameter(f"{value!r} has characters that are not allowed here.")
    return cleaned


@dataclass(slots=True)
class Result:
    """What came back, and everything needed to check it."""

    capability: str
    asks: str
    rows: list[dict[str, Any]]
    columns: list[str]
    #: The query exactly as it ran, filter and all.
    sql: str
    parameters: dict[str, Any]
    #: When it was read. Shown with the figure, because a number without a
    #: time on it is a number somebody will quote next week.
    read_at: dt.datetime
    duration_ms: int
    filter_applied: str
    row_count: int = 0
    #: The rows as they came back, scope column and all. Used to chain one
    #: step to the next and never sent anywhere: an identifier is plumbing,
    #: not an answer, and putting it on screen invites somebody to type it
    #: into the next question.
    raw_rows: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "asks": self.asks,
            "rows": self.rows,
            "columns": self.columns,
            "sql": self.sql,
            "parameters": {
                k: v for k, v in self.parameters.items() if not k.startswith("scope_")
            },
            "read_at": self.read_at.isoformat(),
            "duration_ms": self.duration_ms,
            "filter_applied": self.filter_applied,
            "row_count": self.row_count,
        }


#: Nothing returns more than this. An answer built on ten thousand rows is
#: not an answer, and a question that wants them is a report.
MAX_ROWS = 500


def run(
    session: Session,
    capability: Capability,
    given: dict[str, Any],
    reach: Reach,
) -> Result:
    """Check the role, check the parameters, scope it, run it, timestamp it."""
    may_use(capability, reach)

    parameters: dict[str, Any] = {}
    for parameter in capability.parameters:
        parameters[parameter.name] = _check(parameter, given.get(parameter.name))

    # A LIKE search needs its wildcards added here, not by the caller.
    if capability.name in {"find_customer", "find_supplier"}:
        parameters["text"] = f"%{parameters['text']}%"

    scoped = apply(capability, parameters, reach)

    started = time.perf_counter()
    read_at = dt.datetime.now(dt.timezone.utc)
    cursor = session.execute(text(scoped.sql), scoped.parameters)
    fetched = cursor.mappings().fetchmany(MAX_ROWS + 1)
    duration = int((time.perf_counter() - started) * 1000)

    truncated = len(fetched) > MAX_ROWS
    rows = [dict(row) for row in fetched[:MAX_ROWS]]

    # The scope column is in the result so the filter could bind to it.
    # It is not an answer to anything, so it does not go to the screen.
    shown = [c for c in capability.columns]
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        cleaned.append({key: row.get(key) for key in shown})

    return Result(
        capability=capability.name,
        asks=capability.asks,
        rows=cleaned,
        columns=shown,
        sql=scoped.sql,
        parameters=scoped.parameters,
        read_at=read_at,
        duration_ms=duration,
        filter_applied=scoped.filter_applied
        + (f"; first {MAX_ROWS} rows only" if truncated else ""),
        row_count=len(cleaned),
        raw_rows=rows,
    )
