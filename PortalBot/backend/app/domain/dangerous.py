"""Dangerous goods, and the one thing the bot must never do.

It must never guess a UN number.

A UN number is a legal declaration. Putting the wrong one on a consignment
is not a data error that gets corrected later: it is a false declaration
that can ground an aircraft, void the insurance and land a fine on the
shipper. A system that is ninety-five per cent right about UN numbers is a
system that commits an offence once a fortnight.

So there is a table, the table is keyed on the part, and a part that is
not in the table stops the run and asks a person. There is no inference
step, no nearest match and no default. If the goods look dangerous and the
table is silent, that is an exception, not a judgement call.

The entries below are the common ones for an industrial distributor:
aerosol maintenance products, lithium cells inside electronic parts, and
the adhesives and solvents that go with them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Declaration:
    un_number: str
    proper_name: str
    dg_class: str
    packing_group: str
    #: Set when the item ships under a relief that removes the full
    #: declaration, which is not the same as not being dangerous.
    limited_quantity: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "un_number": self.un_number,
            "proper_name": self.proper_name,
            "dg_class": self.dg_class,
            "packing_group": self.packing_group,
            "limited_quantity": self.limited_quantity,
            "note": self.note,
        }


#: Keyed on the part, not on a word in its description. A description is
#: marketing text; a part number is a decision somebody made once.
TABLE: dict[str, Declaration] = {
    "HT-AER-PTFE-400": Declaration(
        "UN1950", "Aerosols, flammable", "2.1", "—",
        note="Dry film lubricant, 400ml aerosol.",
    ),
    "HT-AER-ZINC-500": Declaration(
        "UN1950", "Aerosols, flammable", "2.1", "—",
        note="Cold galvanising spray.",
    ),
    "HT-AER-CLEAN-600": Declaration(
        "UN1950", "Aerosols, non-flammable", "2.2", "—",
        note="Contact cleaner, non-flammable propellant.",
    ),
    "HT-ADH-THRD-050": Declaration(
        "UN1133", "Adhesives, flammable", "3", "II",
        limited_quantity=True,
        note="Threadlocker, 50ml. Ships as a limited quantity.",
    ),
    "HT-SOL-DEGR-005": Declaration(
        "UN1993", "Flammable liquid, not otherwise specified", "3", "III",
        note="Parts degreaser, 5 litre.",
    ),
    "HT-SEN-PROX-LI": Declaration(
        "UN3481", "Lithium ion batteries contained in equipment", "9", "—",
        note="Proximity sensor with an internal cell. Contained in equipment, "
        "which is a different entry from a loose cell.",
    ),
    "HT-BAT-CR2032-10": Declaration(
        "UN3480", "Lithium ion batteries", "9", "II",
        note="Loose cells. Not the same entry as cells inside equipment.",
    ),
}

#: Words that mean "look this up", not words that mean "it is this".
#: Their only job is to catch a part that should have been in the table
#: and is not.
SUSPICIOUS = re.compile(
    r"\b(aerosol|spray|propellant|flammable|lithium|battery|cell|"
    r"adhesive|solvent|degreas|thinner|paint|lacquer|gas|corrosiv)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class Finding:
    """What the goods are, or why nobody here can say."""

    dangerous: bool
    declarations: list[Declaration] = field(default_factory=list)
    #: Parts that look dangerous and are not in the table. These stop the
    #: run. They are never guessed at.
    unknown: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def needs_a_person(self) -> bool:
        return bool(self.unknown)

    def to_dict(self) -> dict[str, object]:
        return {
            "dangerous": self.dangerous,
            "declarations": [d.to_dict() for d in self.declarations],
            "unknown": self.unknown,
            "needs_a_person": self.needs_a_person,
            "reasons": self.reasons,
        }


def assess(lines: list[dict[str, object]]) -> Finding:
    """Look every part up. Never infer one.

    ``lines`` is the packing record: part code and description per line.
    """
    found = Finding(dangerous=False)

    for line in lines:
        part = str(line.get("part_code", "")).strip().upper()
        description = str(line.get("description", ""))

        declaration = TABLE.get(part)
        if declaration is not None:
            found.dangerous = True
            if declaration not in found.declarations:
                found.declarations.append(declaration)
            found.reasons.append(f"{part} is {declaration.un_number} by the table")
            continue

        if SUSPICIOUS.search(description) or SUSPICIOUS.search(part):
            # The whole point. It looks dangerous and nobody has decided
            # what it is, so the bot stops.
            found.unknown.append(part or description[:40])
            found.reasons.append(
                f"{part or description[:30]!r} reads as dangerous goods and is "
                "not in the table"
            )

    return found


def declaration_for(parts: list[str]) -> Declaration | None:
    """The single declaration to put on the form.

    A consignment with two different UN numbers is not something to
    average. It goes to a person.
    """
    found = [TABLE[p.upper()] for p in parts if p.upper() in TABLE]
    unique = {d.un_number: d for d in found}
    if len(unique) == 1:
        return next(iter(unique.values()))
    return None
