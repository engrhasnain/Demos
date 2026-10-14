"""Checking an address before the portal has to refuse it.

Every refusal the portal makes costs a round trip and, in a real run, a
rate-limit slot. Most of them are preventable: a Taiwan postcode with four
digits, a United States ZIP with a letter in it, a city that is actually
a district. Catching those here turns a portal exception into a local one
with a clear reason, which is the difference between "something went
wrong" and "the postcode has four digits and Taiwan uses three or five".

What this does not do is invent an address. A postcode that cannot be
tidied is an exception, not a best guess. Shipping a pallet to a guessed
postcode is how it ends up in the wrong city.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: What each country's postcode looks like, and how to tidy it.
RULES: dict[str, dict[str, object]] = {
    "TW": {
        "pattern": re.compile(r"^\d{3}(\d{2})?$"),
        "tidy": lambda value: re.sub(r"\D", "", value),
        "says": "three digits, or five",
    },
    "US": {
        "pattern": re.compile(r"^\d{5}(-\d{4})?$"),
        "tidy": lambda value: (
            re.sub(r"[^\d-]", "", value).strip("-")
        ),
        "says": "five digits, optionally plus four",
    },
    "JP": {
        "pattern": re.compile(r"^\d{3}-\d{4}$"),
        "tidy": lambda value: (
            f"{re.sub(r'\\D', '', value)[:3]}-{re.sub(r'\\D', '', value)[3:7]}"
            if len(re.sub(r"\D", "", value)) == 7
            else value.strip()
        ),
        "says": "three digits, a hyphen, four digits",
    },
    "DE": {
        "pattern": re.compile(r"^\d{5}$"),
        "tidy": lambda value: re.sub(r"\D", "", value),
        "says": "five digits",
    },
}

#: Characters the portal's own form rejects, which are easier to catch here.
AWKWARD = re.compile(r"[<>\"\\\x00-\x1f]")


@dataclass(slots=True)
class Checked:
    ok: bool
    postcode: str
    kind: str = ""
    summary: str = ""
    tidied: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "postcode": self.postcode,
            "kind": self.kind,
            "summary": self.summary,
            "tidied": self.tidied,
        }


def validate(
    *, name: str, line1: str, city: str, postcode: str, country: str
) -> Checked:
    """Is this address one the portal will take?"""
    country = (country or "").strip().upper()
    postcode = (postcode or "").strip()

    for label, value in (("name", name), ("address", line1), ("city", city)):
        if not (value or "").strip():
            return Checked(False, postcode, "bad_address", f"No {label}.")
        if AWKWARD.search(value):
            return Checked(
                False, postcode, "bad_address",
                f"The {label} has characters the portal will not accept.",
            )

    rule = RULES.get(country)
    if rule is None:
        # A country nobody has written a rule for is not a reason to stop,
        # but it is a reason not to claim the postcode was checked.
        return Checked(
            True, postcode, "", f"No postcode rule for {country}; sent as given."
        )

    pattern = rule["pattern"]
    if pattern.match(postcode):
        return Checked(True, postcode, "", "Address looks right.")

    tidied = str(rule["tidy"](postcode))
    if pattern.match(tidied):
        return Checked(
            True, tidied, "", f"Postcode tidied to {tidied}.", tidied=True
        )

    return Checked(
        False,
        postcode,
        "bad_postcode",
        f"{postcode!r} is not a {country} postcode, which is {rule['says']}.",
    )
