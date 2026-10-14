"""The bot: two systems, no transaction between them.

The booking happens in the carrier's portal. The write-back happens in the
business system. There is no transaction spanning the two, and there never
will be, because one of them is somebody else's website.

So the row is the transaction. Each shipment carries its own state, and the
state advances only after the system it describes has confirmed:

    pending  ──book──▶  booked  ──write back──▶  written_back  ──▶  done

Kill the process anywhere in that line and the row says exactly how far it
got. The next run reads the row first and resumes, and because the key is
derived from the shipment rather than generated, a repeat is free.

Three habits that matter more than the happy path:

**It asks the portal before it assumes.** Even with a clean local state,
the first thing a booking does is ask the carrier whether this reference
is already there. Local state can be lost; the carrier's cannot.

**It never widens a failure.** An exception on one shipment is recorded
against that shipment and the run carries on. One bad address does not
stop the other hundred and seventy-nine.

**It stops the whole run for exactly one thing:** the form changing shape.
That is the only failure where carrying on makes things worse.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..domain import dangerous, drift
from ..models import Challenge, Run, ScriptFlag, Shipment, Step, User
from ..systems.carrier import (
    Behaviour,
    CarrierPortal,
    NeedsCode,
    PortalDown,
    PortalError,
)
from ..systems.legacy import LegacyError, LegacySystem, RecordLocked, StaleWrite

#: What the booking script was written against.
EXPECTED = drift.Expectation(
    name="carrier_booking_form",
    version="2026.03",
    fields=sorted(
        [
            "consignment_ref", "service_code", "collect_on", "deliver_name",
            "deliver_addr1", "deliver_city", "deliver_post", "deliver_ctry",
            "pkg_count", "gross_kg", "goods_desc", "has_dg", "dg_un",
            "dg_class", "dg_pg",
        ]
    ),
)

#: Every way a shipment can fail, named. "Something went wrong" is not an
#: exception kind; it is an admission that nobody looked.
EXCEPTION_WORDS: dict[str, str] = {
    "bad_address": "Address will not validate",
    "bad_postcode": "Postcode wrong for the country",
    "undeclared_dangerous_goods": "Dangerous goods not declared",
    "unknown_dangerous_goods": "Dangerous goods not in the table",
    "mixed_dangerous_goods": "More than one UN number",
    "overweight_package": "Package over the weight limit",
    "bad_weight": "Weight missing or wrong",
    "bad_packages": "Package count wrong",
    "portal_down": "The portal did not answer",
    "rate_limited": "The portal rate limited us",
    "needs_code": "Waiting for a one-time code",
    "legacy_locked": "The record is open on somebody's screen",
    "legacy_stale": "The record changed while we held it",
    "legacy_not_found": "No such order in the business system",
    "legacy_down": "The business system did not answer",
    "tracking_timeout": "The tracking number did not appear in time",
    "truncated_write": "The business system truncated the tracking number",
    "form_changed": "The booking form has changed shape",
    "unknown": "Not classified",
}


def key_for(shipment: Shipment) -> str:
    """The same shipment always computes the same key.

    Derived, not generated. A generated key is a new key every run, which
    is exactly what makes a retry book twice.
    """
    parts = [
        shipment.order_number,
        shipment.to_name,
        shipment.to_postcode,
        str(shipment.packages),
        f"{shipment.weight_kg:.3f}",
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


@dataclass
class Outcome:
    shipment: Shipment
    state: str
    exception_kind: str = ""
    detail: str = ""
    skipped: bool = False


class Stopped(Exception):
    """The run stopped itself. Only drift does this."""

    def __init__(self, reason: str, detail: dict[str, Any]) -> None:
        super().__init__(reason)
        self.detail = detail


class Bot:
    """Drives both systems, and keeps a trace of everything it did."""

    def __init__(
        self,
        session: Session,
        carrier: CarrierPortal,
        legacy: LegacySystem,
        *,
        run: Run | None = None,
        clock: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self.session = session
        self.carrier = carrier
        self.legacy = legacy
        self.run = run
        self.now = clock or (lambda: dt.datetime.now(dt.timezone.utc))
        self.random = random.Random(31)

    # ------------------------------------------------------------------
    def note(
        self,
        shipment: Shipment,
        *,
        system: str,
        action: str,
        outcome: str,
        sent: dict[str, Any] | None = None,
        received: dict[str, Any] | None = None,
        note: str = "",
        attempt: int = 1,
        duration_ms: int = 0,
    ) -> Step:
        step = Step(
            shipment_id=shipment.id,
            run_id=self.run.id if self.run else None,
            system=system,
            action=action,
            attempt=attempt,
            outcome=outcome,
            sent=_plain(sent or {}),
            received=_plain(received or {}),
            note=note[:400],
            duration_ms=duration_ms,
        )
        self.session.add(step)
        self.session.flush()
        return step

    # ------------------------------------------------------------------
    def check_the_form(self) -> drift.Drift:
        """Before anything else, is the form still the one we know?"""
        shape = self.carrier.shape()
        found = drift.compare(EXPECTED, shape["fields"])
        if found.matches:
            return found

        flag = ScriptFlag(
            run_id=self.run.id if self.run else None,
            script=EXPECTED.name,
            expected_fingerprint=found.expected_fingerprint,
            found_fingerprint=found.found_fingerprint,
            detail=found.to_dict(),
            status="open",
        )
        self.session.add(flag)
        self.session.flush()
        raise Stopped(found.summary(), found.to_dict())

    # ------------------------------------------------------------------
    def handle(self, shipment: Shipment) -> Outcome:
        """One shipment, from wherever it got to last time."""
        shipment.attempts += 1

        # Already finished. Nothing to do, and saying so is not a failure.
        if shipment.state == "done":
            self.note(shipment, system="bot", action="skip", outcome="skipped",
                      note="already done")
            return Outcome(shipment, "done", skipped=True)

        try:
            if shipment.state in {"pending", "needs_a_person", "failed"}:
                self._prepare(shipment)
                self._book(shipment)
            if shipment.state == "booked":
                self._collect(shipment)
            if shipment.state == "booked" and shipment.tracking_number:
                self._write_back(shipment)
            if shipment.state == "written_back":
                shipment.state = "done"
                self.session.flush()
            return Outcome(shipment, shipment.state)
        except _Exception as error:
            shipment.state = "needs_a_person" if error.needs_a_person else "failed"
            shipment.exception_kind = error.kind
            shipment.exception_detail = str(error)
            self.session.flush()
            return Outcome(shipment, shipment.state, error.kind, str(error))

    # ------------------------------------------------------------------
    def _prepare(self, shipment: Shipment) -> None:
        """Everything that can be checked before the portal is involved."""
        from .addresses import validate

        address = validate(
            name=shipment.to_name,
            line1=shipment.to_line1,
            city=shipment.to_city,
            postcode=shipment.to_postcode,
            country=shipment.to_country,
        )
        self.note(
            shipment,
            system="bot",
            action="validate_address",
            outcome="ok" if address.ok else "refused",
            received=address.to_dict(),
            note=address.summary,
        )
        if not address.ok:
            raise _Exception(address.kind or "bad_address", address.summary, needs_a_person=True)
        # The portal is fussy about format; send it the tidy one.
        shipment.to_postcode = address.postcode

        found = dangerous.assess(shipment.lines or [])
        shipment.dangerous = found.dangerous
        shipment.dangerous_detail = found.to_dict()
        self.note(
            shipment,
            system="bot",
            action="assess_dangerous_goods",
            outcome="refused" if found.needs_a_person else "ok",
            received=found.to_dict(),
            note="; ".join(found.reasons[:3]),
        )
        if found.needs_a_person:
            raise _Exception(
                "unknown_dangerous_goods",
                f"{', '.join(found.unknown)} reads as dangerous goods and is not "
                "in the table. A UN number is a legal declaration and is never "
                "guessed.",
                needs_a_person=True,
            )
        if found.dangerous and len({d.un_number for d in found.declarations}) > 1:
            raise _Exception(
                "mixed_dangerous_goods",
                "More than one UN number on one consignment.",
                needs_a_person=True,
            )
        self.session.flush()

    # ------------------------------------------------------------------
    def _book(self, shipment: Shipment) -> None:
        """Book it, having first asked whether we already did."""
        # Local state can be lost. The carrier's cannot. This single call
        # is what makes killing the process mid-run harmless.
        already = self.carrier.find(shipment.reference)
        if already is not None:
            shipment.consignment = already.consignment
            shipment.state = "booked"
            shipment.booked_at = already.booked_at
            self.note(
                shipment,
                system="carrier",
                action="book",
                outcome="skipped",
                received={"consignment": already.consignment},
                note="the carrier already has this reference; not booking again",
            )
            self.session.flush()
            return

        form = self._form_for(shipment)
        attempt = 0
        while True:
            attempt += 1
            started = time.perf_counter()
            try:
                booking = self.carrier.book(form)
            except NeedsCode as challenge:
                self._ask_for_a_code(shipment, challenge.challenge_id)
                raise _Exception(
                    "needs_code",
                    "The portal asked for a one-time code. Somebody on duty has "
                    "been asked for it.",
                    needs_a_person=True,
                )
            except PortalDown as error:
                self.note(shipment, system="carrier", action="book", outcome="failed",
                          attempt=attempt, note=str(error))
                if attempt >= settings.max_attempts:
                    raise _Exception("portal_down", str(error)) from error
                self._wait(attempt)
                continue
            except PortalError as error:
                self.note(
                    shipment,
                    system="carrier",
                    action="book",
                    outcome="refused",
                    sent=form,
                    received={"code": error.code, "message": str(error)},
                    attempt=attempt,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
                if error.code == "duplicate":
                    # The portal's own guard caught it. Recover rather than fail.
                    existing = self.carrier.find(shipment.reference)
                    if existing:
                        shipment.consignment = existing.consignment
                        shipment.state = "booked"
                        self.session.flush()
                        return
                if error.code in {"rate_limited", "server_error"} and attempt < settings.max_attempts:
                    self._wait(attempt)
                    continue
                raise _Exception(
                    error.code,
                    str(error),
                    needs_a_person=error.code
                    not in {"rate_limited", "server_error"},
                ) from error

            self.note(
                shipment,
                system="carrier",
                action="book",
                outcome="ok",
                sent=form,
                received={"consignment": booking.consignment},
                attempt=attempt,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            shipment.consignment = booking.consignment
            shipment.booked_at = booking.booked_at
            shipment.carrier = settings.carrier_name
            # The checkpoint. Everything before this can be repeated for
            # free; everything after it knows the booking exists.
            shipment.state = "booked"
            self.session.flush()
            return

    def _form_for(self, shipment: Shipment) -> dict[str, Any]:
        names = self.carrier.fields
        declaration = (
            dangerous.declaration_for([l.get("part_code", "") for l in shipment.lines or []])
            if shipment.dangerous
            else None
        )
        form: dict[str, Any] = {
            names["reference"]: shipment.reference,
            names["service"]: shipment.service,
            names["collection_date"]: self.now().date().isoformat(),
            names["to_name"]: shipment.to_name,
            names["to_line1"]: shipment.to_line1,
            names["to_city"]: shipment.to_city,
            names["to_postcode"]: shipment.to_postcode,
            names["to_country"]: shipment.to_country,
            names["packages"]: shipment.packages,
            names["weight_kg"]: shipment.weight_kg,
            names["goods_description"]: shipment.goods_description,
            names["dangerous"]: "yes" if shipment.dangerous else "no",
        }
        if declaration is not None:
            form[names["un_number"]] = declaration.un_number
            form[names["dg_class"]] = declaration.dg_class
            form[names["dg_packing_group"]] = declaration.packing_group
        return form

    # ------------------------------------------------------------------
    def _collect(self, shipment: Shipment) -> None:
        """Poll for the tracking number, with a timeout rather than a sleep."""
        deadline = time.perf_counter() + settings.tracking_timeout_seconds
        attempt = 0
        while True:
            attempt += 1
            try:
                booking = self.carrier.collect(shipment.consignment)
            except (PortalError, PortalDown) as error:
                self.note(shipment, system="carrier", action="collect",
                          outcome="failed", attempt=attempt, note=str(error))
                if time.perf_counter() >= deadline:
                    raise _Exception("tracking_timeout", str(error)) from error
                self._wait(attempt)
                continue

            if booking.tracking_number:
                self.note(
                    shipment,
                    system="carrier",
                    action="collect",
                    outcome="ok",
                    received={"tracking_number": booking.tracking_number},
                    attempt=attempt,
                )
                shipment.tracking_number = booking.tracking_number
                shipment.label_url = booking.label_url
                self.session.flush()
                return

            if time.perf_counter() >= deadline:
                self.note(shipment, system="carrier", action="collect",
                          outcome="waiting", attempt=attempt,
                          note="still processing when the timeout ran out")
                raise _Exception(
                    "tracking_timeout",
                    "The carrier had not produced a tracking number in time. "
                    "The booking stands; this will resume.",
                )
            self._wait(attempt, cap=0.05)

    # ------------------------------------------------------------------
    def _write_back(self, shipment: Shipment) -> None:
        """Put the tracking number back, and check that it arrived whole."""
        attempt = 0
        while True:
            attempt += 1
            try:
                record = self.legacy.read(shipment.order_number)
                written = self.legacy.write_tracking(
                    record.order,
                    tracking_number=shipment.tracking_number,
                    carrier=shipment.carrier,
                    revision=record.revision,
                )
            except RecordLocked as error:
                self.note(shipment, system="legacy", action="write_tracking",
                          outcome="refused", attempt=attempt, note=str(error))
                if attempt >= settings.max_attempts:
                    raise _Exception("legacy_locked", str(error)) from error
                self._wait(attempt)
                continue
            except StaleWrite as error:
                self.note(shipment, system="legacy", action="write_tracking",
                          outcome="refused", attempt=attempt, note=str(error))
                if attempt >= settings.max_attempts:
                    raise _Exception("legacy_stale", str(error)) from error
                continue  # read it again immediately
            except LegacyError as error:
                self.note(shipment, system="legacy", action="write_tracking",
                          outcome="failed", attempt=attempt, note=str(error))
                kind = {
                    "not_found": "legacy_not_found",
                    "down": "legacy_down",
                }.get(error.code, "unknown")
                if kind == "legacy_down" and attempt < settings.max_attempts:
                    self._wait(attempt)
                    continue
                raise _Exception(kind, str(error), needs_a_person=kind != "legacy_down") from error

            # Read it back. The screen truncates silently, and a write that
            # succeeded with half a tracking number is worse than one that
            # failed, because nobody goes looking for it.
            if written.tracking_number != shipment.tracking_number:
                self.note(
                    shipment,
                    system="legacy",
                    action="verify_write",
                    outcome="refused",
                    sent={"tracking_number": shipment.tracking_number},
                    received={"tracking_number": written.tracking_number},
                    note="the system stored something other than what was sent",
                )
                raise _Exception(
                    "truncated_write",
                    f"Sent {shipment.tracking_number!r}, the system kept "
                    f"{written.tracking_number!r}.",
                    needs_a_person=True,
                )

            self.note(
                shipment,
                system="legacy",
                action="write_tracking",
                outcome="ok",
                sent={"order": record.order, "tracking_number": shipment.tracking_number},
                received={"revision": written.revision},
                attempt=attempt,
            )
            shipment.written_back_at = self.now()
            shipment.state = "written_back"
            self.session.flush()
            return

    # ------------------------------------------------------------------
    def _ask_for_a_code(self, shipment: Shipment, external_id: str) -> Challenge:
        """Push to whoever is on duty. Never try to answer it."""
        on_duty = self.session.scalar(select(User).where(User.on_duty.is_(True)))
        challenge = Challenge(
            reference=f"OTP-{external_id}",
            shipment_id=shipment.id,
            run_id=self.run.id if self.run else None,
            kind="one_time_code",
            asked_of_id=on_duty.id if on_duty else None,
            external_id=external_id,
            status="waiting",
            note="The portal asked for a one-time code.",
        )
        self.session.add(challenge)
        self.note(
            shipment,
            system="bot",
            action="ask_for_code",
            outcome="waiting",
            received={"challenge": external_id, "asked_of": on_duty.full_name if on_duty else None},
            note="pushed to the clerk on duty; the bot does not guess codes",
        )
        self.session.flush()
        return challenge

    def _wait(self, attempt: int, cap: float = 0.08) -> None:
        """Back off, with jitter, so a hundred retries do not arrive together."""
        base = min(cap, settings.backoff_seconds * (2 ** (attempt - 1)))
        time.sleep(base * (0.5 + self.random.random() * 0.5))


class _Exception(Exception):
    def __init__(self, kind: str, message: str, *, needs_a_person: bool = False) -> None:
        super().__init__(message)
        self.kind = kind
        self.needs_a_person = needs_a_person


def _plain(value: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, (str, int, float, bool)) or item is None:
            out[key] = item
        else:
            out[key] = str(item)[:300]
    return out
