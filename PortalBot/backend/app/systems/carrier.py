"""A carrier booking portal, with all of its bad habits.

This is not a mock. It is a small, stateful system with its own rules, its
own validation, its own session handling and its own idea of what a good
request looks like — and the bot drives it over HTTP exactly as it would
drive a real one. Everything the automation has to cope with is in here
because this thing does it, not because a test asserted it:

* it rejects a shipment whose weight does not match its packages;
* it will not take an aerosol without a declaration, and will not take a
  declaration with a UN number that does not match the goods;
* it rate limits, and goes slow, and sometimes falls over;
* it asks for a one-time code when it does not recognise the session;
* it books asynchronously, so the tracking number is not in the response;
* and it can be told to change its own field names, which is how an
  automation really dies.

Keeping it honest matters. A simulator that always says yes proves the bot
works on a portal that does not exist.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any

#: The portal's own idea of what a booking looks like. The names here are
#: what the bot's selectors point at, and `drift` changes them.
FIELDS_V1: dict[str, str] = {
    "reference": "consignment_ref",
    "service": "service_code",
    "collection_date": "collect_on",
    "to_name": "deliver_name",
    "to_line1": "deliver_addr1",
    "to_city": "deliver_city",
    "to_postcode": "deliver_post",
    "to_country": "deliver_ctry",
    "packages": "pkg_count",
    "weight_kg": "gross_kg",
    "goods_description": "goods_desc",
    "dangerous": "has_dg",
    "un_number": "dg_un",
    "dg_class": "dg_class",
    "dg_packing_group": "dg_pg",
}

#: What the portal looks like after a release. One field renamed and one
#: moved: small enough that a bot built on positions carries on and books
#: nonsense, which is the failure that costs money.
FIELDS_V2: dict[str, str] = {
    **FIELDS_V1,
    "to_postcode": "deliver_postcode",   # renamed
    "weight_kg": "gross_weight_kg",      # renamed
}


class PortalError(Exception):
    """Something the portal said no to, in its own words."""

    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class PortalDown(Exception):
    """It did not answer at all."""


class NeedsCode(Exception):
    """It wants a one-time code before it will do anything."""

    def __init__(self, challenge_id: str) -> None:
        super().__init__("A one-time code is required.")
        self.challenge_id = challenge_id


@dataclass
class Booking:
    consignment: str
    reference: str
    status: str
    tracking_number: str = ""
    label_url: str = ""
    booked_at: dt.datetime | None = None
    #: Bookings are not instant. The tracking number turns up later, which
    #: is why the bot polls rather than sleeping for a guessed interval.
    ready_at: dt.datetime | None = None


@dataclass
class Behaviour:
    """How badly the portal is behaving today. The demonstration sets these."""

    #: Which field names it is using.
    version: str = "v1"
    #: Chance any given request simply fails.
    failure_rate: float = 0.0
    #: Chance it is slow enough to matter.
    slow_rate: float = 0.0
    slow_seconds: float = 0.0
    #: Chance it demands a one-time code.
    challenge_rate: float = 0.0
    #: How long after booking the tracking number appears.
    tracking_delay_seconds: float = 0.0
    #: Requests allowed per run before it starts refusing.
    rate_limit: int = 0
    down: bool = False


class CarrierPortal:
    """One carrier's booking system, as it actually behaves."""

    def __init__(self, *, seed: int = 11, behaviour: Behaviour | None = None) -> None:
        self.random = random.Random(seed)
        self.behaviour = behaviour or Behaviour()
        self.bookings: dict[str, Booking] = {}
        #: The portal's own duplicate guard, keyed on the reference the
        #: caller supplies. Real portals have one; relying on it alone is
        #: still wrong, because the bot has to know what it already did.
        self.by_reference: dict[str, str] = {}
        self.requests = 0
        self.challenges: dict[str, bool] = {}
        self.log: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    @property
    def fields(self) -> dict[str, str]:
        return FIELDS_V2 if self.behaviour.version == "v2" else FIELDS_V1

    def shape(self) -> dict[str, Any]:
        """What the booking form looks like right now.

        The bot reads this before it fills anything in, and compares it
        against the shape its script was written for.
        """
        self._maybe_misbehave("shape")
        names = sorted(self.fields.values())
        return {
            "version": self.behaviour.version,
            "fields": names,
            "fingerprint": hashlib.sha256("|".join(names).encode()).hexdigest()[:16],
        }

    # ------------------------------------------------------------------
    def _maybe_misbehave(self, what: str) -> None:
        self.requests += 1
        behaviour = self.behaviour

        if behaviour.down:
            raise PortalDown("The portal is not responding.")
        if behaviour.rate_limit and self.requests > behaviour.rate_limit:
            raise PortalError(
                "rate_limited",
                "Too many requests. Try again shortly.",
                status=429,
            )
        if behaviour.failure_rate and self.random.random() < behaviour.failure_rate:
            raise PortalError("server_error", "The portal had a problem.", status=503)
        if behaviour.slow_rate and self.random.random() < behaviour.slow_rate:
            time.sleep(min(behaviour.slow_seconds, 0.05))  # kept short in a demo
        if (
            behaviour.challenge_rate
            and what == "book"
            and self.random.random() < behaviour.challenge_rate
        ):
            challenge = f"CH-{self.random.randint(100000, 999999)}"
            self.challenges[challenge] = False
            raise NeedsCode(challenge)

    def answer_challenge(self, challenge_id: str, code: str) -> bool:
        """Only a real six digit code gets through, and only once."""
        if challenge_id not in self.challenges:
            return False
        if not re.fullmatch(r"\d{6}", code or ""):
            return False
        self.challenges[challenge_id] = True
        return True

    # ------------------------------------------------------------------
    def book(self, form: dict[str, Any], *, challenge_id: str = "") -> Booking:
        """Take a booking, or say exactly why not.

        Every refusal here is one a real portal makes, with a code the bot
        can classify rather than a sentence it has to read.
        """
        if challenge_id and not self.challenges.get(challenge_id):
            raise PortalError("challenge_unanswered", "The code was not accepted.")
        if not challenge_id:
            self._maybe_misbehave("book")

        names = self.fields
        reference = str(form.get(names["reference"], "")).strip()
        if not reference:
            raise PortalError("missing_reference", "No consignment reference.")

        # The portal's own duplicate guard. The bot does not rely on it.
        if reference in self.by_reference:
            existing = self.bookings[self.by_reference[reference]]
            self.log.append({"what": "duplicate_refused", "reference": reference})
            raise PortalError(
                "duplicate",
                f"Consignment {reference} is already booked as {existing.consignment}.",
                status=409,
            )

        # --- the ordinary validation --------------------------------
        for key in ("to_name", "to_line1", "to_city", "to_country"):
            if not str(form.get(names[key], "")).strip():
                raise PortalError(
                    "missing_field", f"{names[key]} is required.", status=422
                )

        country = str(form.get(names["to_country"], "")).upper()
        postcode = str(form.get(names["to_postcode"], "")).strip()
        if country == "US" and not re.fullmatch(r"\d{5}(-\d{4})?", postcode):
            raise PortalError(
                "bad_postcode", f"{postcode!r} is not a United States ZIP code.", status=422
            )
        if country == "TW" and not re.fullmatch(r"\d{3}(\d{2})?", postcode):
            raise PortalError(
                "bad_postcode", f"{postcode!r} is not a Taiwan postcode.", status=422
            )

        try:
            packages = int(form.get(names["packages"], 0))
            weight = float(form.get(names["weight_kg"], 0))
        except (TypeError, ValueError) as error:
            raise PortalError("bad_number", "Packages and weight must be numbers.", status=422) from error

        if packages < 1:
            raise PortalError("bad_packages", "At least one package.", status=422)
        if weight <= 0:
            raise PortalError("bad_weight", "Weight must be above zero.", status=422)
        # A real portal checks this and a clerk re-keying gets it wrong.
        if weight / packages > 70:
            raise PortalError(
                "overweight_package",
                f"{weight}kg over {packages} packages is more than 70kg each.",
                status=422,
            )

        # --- dangerous goods -----------------------------------------
        declared = str(form.get(names["dangerous"], "")).lower() in {"1", "true", "yes", "y"}
        un_number = str(form.get(names["un_number"], "")).strip().upper()
        description = str(form.get(names["goods_description"], "")).lower()

        looks_dangerous = any(
            word in description
            for word in ("aerosol", "spray", "lithium", "battery", "flammable", "adhesive")
        )
        if looks_dangerous and not declared:
            raise PortalError(
                "undeclared_dangerous_goods",
                f"{description!r} looks like dangerous goods and nothing was declared.",
                status=422,
            )
        if declared:
            if not re.fullmatch(r"UN\d{4}", un_number):
                raise PortalError(
                    "bad_un_number",
                    f"{un_number!r} is not a UN number.",
                    status=422,
                )
            if not str(form.get(names["dg_class"], "")).strip():
                raise PortalError("missing_dg_class", "A class is required.", status=422)

        # --- booked ---------------------------------------------------
        consignment = f"CN{self.random.randint(10**9, 10**10 - 1)}"
        now = dt.datetime.now(dt.timezone.utc)
        booking = Booking(
            consignment=consignment,
            reference=reference,
            status="accepted",
            booked_at=now,
            ready_at=now
            + dt.timedelta(seconds=self.behaviour.tracking_delay_seconds),
        )
        self.bookings[consignment] = booking
        self.by_reference[reference] = consignment
        self.log.append({"what": "booked", "reference": reference, "consignment": consignment})
        return booking

    # ------------------------------------------------------------------
    def collect(self, consignment: str) -> Booking:
        """The tracking number, once the portal has got round to it.

        It is not in the booking response, which is why the bot polls with
        a timeout rather than sleeping for a number somebody guessed.
        """
        self._maybe_misbehave("collect")
        booking = self.bookings.get(consignment)
        if booking is None:
            raise PortalError("unknown_consignment", "No such consignment.", status=404)
        if booking.ready_at and dt.datetime.now(dt.timezone.utc) < booking.ready_at:
            booking.status = "processing"
            return booking
        if not booking.tracking_number:
            booking.tracking_number = f"HT{self.random.randint(10**9, 10**10 - 1)}"
            booking.label_url = f"https://carrier.example/labels/{booking.consignment}.pdf"
            booking.status = "ready"
        return booking

    def find(self, reference: str) -> Booking | None:
        """Has this reference already been booked? Used to recover a run."""
        consignment = self.by_reference.get(reference)
        return self.bookings.get(consignment) if consignment else None
