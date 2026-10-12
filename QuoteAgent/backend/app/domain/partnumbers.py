"""Reading industrial part descriptions the way a sales engineer reads them.

Three families, because that is what Hengtai Industrial Supply sells:

* **Fasteners** written to a published standard, for example
  ``DIN 912 M8x30 12.9 zinc`` or ``ISO 4762 M8-1.25 x 30 cl.12.9 A2K``.
* **Deep groove ball bearings**, for example ``6204-2RS C3``. ISO 15:2017 fixes
  the dimensions, so a 6204 is 20 x 47 x 14 mm from every maker; only the seal
  suffix changes between brands (SKF ``2RS1``, FAG ``2RSR``, NSK ``DDU``,
  NTN ``LLU``, Timken ``2RS``).
* **Pneumatic cylinders and valves**, for example ``ISO 15552 cylinder 32 bore
  50 stroke``.

Everything here is deterministic. The reasoning engine may *propose* a reading;
this module is what *verifies* it, attribute by attribute.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

#: Published standard -> the canonical product it describes.
FASTENER_STANDARDS: dict[str, dict[str, str]] = {
    "ISO 4762": {"kind": "socket_head_cap_screw", "head": "cylindrical", "drive": "hexagon_socket"},
    "DIN 912": {"kind": "socket_head_cap_screw", "head": "cylindrical", "drive": "hexagon_socket"},
    # A fully threaded bolt and a partially threaded one are different parts
    # with different standards, and quoting one for the other is a return.
    "ISO 4017": {"kind": "hex_head_bolt", "head": "hexagon", "drive": "hexagon"},
    "DIN 933": {"kind": "hex_head_bolt", "head": "hexagon", "drive": "hexagon"},
    "ISO 4014": {"kind": "hex_head_bolt_partial", "head": "hexagon", "drive": "hexagon"},
    "DIN 931": {"kind": "hex_head_bolt_partial", "head": "hexagon", "drive": "hexagon"},
    "ISO 4032": {"kind": "hex_nut", "head": "hexagon", "drive": "hexagon"},
    "DIN 934": {"kind": "hex_nut", "head": "hexagon", "drive": "hexagon"},
    "ISO 7089": {"kind": "flat_washer", "head": "", "drive": ""},
    "DIN 125": {"kind": "flat_washer", "head": "", "drive": ""},
    "ISO 7380": {"kind": "button_head_screw", "head": "button", "drive": "hexagon_socket"},
    "ISO 10642": {"kind": "countersunk_socket_screw", "head": "countersunk", "drive": "hexagon_socket"},
    "DIN 7991": {"kind": "countersunk_socket_screw", "head": "countersunk", "drive": "hexagon_socket"},
    "ISO 4026": {"kind": "socket_set_screw", "head": "none", "drive": "hexagon_socket"},
    "DIN 913": {"kind": "socket_set_screw", "head": "none", "drive": "hexagon_socket"},
    "ISO 7040": {"kind": "prevailing_torque_nut", "head": "hexagon", "drive": "hexagon"},
    "DIN 985": {"kind": "prevailing_torque_nut", "head": "hexagon", "drive": "hexagon"},
    "DIN 976": {"kind": "threaded_stud", "head": "none", "drive": "none"},
    "DIN 975": {"kind": "threaded_stud", "head": "none", "drive": "none"},
    "DIN 127": {"kind": "spring_washer", "head": "", "drive": ""},
}

#: Standards that describe the same part. Quoting either is correct.
EQUIVALENT_STANDARDS: dict[str, str] = {
    "DIN 912": "ISO 4762",
    "DIN 913": "ISO 4026",
    "DIN 985": "ISO 7040",
    "DIN 975": "DIN 976",
    "DIN 933": "ISO 4017",
    "DIN 931": "ISO 4014",
    "DIN 934": "ISO 4032",
    "DIN 125": "ISO 7089",
    "DIN 7991": "ISO 10642",
}

#: Coarse pitch in millimetres for the common metric thread sizes (ISO 261).
COARSE_PITCH: dict[str, str] = {
    "M3": "0.5", "M4": "0.7", "M5": "0.8", "M6": "1.0", "M8": "1.25",
    "M10": "1.5", "M12": "1.75", "M14": "2.0", "M16": "2.0", "M18": "2.5",
    "M20": "2.5", "M22": "2.5", "M24": "3.0", "M27": "3.0", "M30": "3.5",
}

#: Nominal thread diameter in millimetres, used for the duty classification
#: split at 6 mm between commodity codes 7318.15.60 and 7318.15.80.
THREAD_DIAMETER_MM: dict[str, float] = {
    "M3": 3, "M4": 4, "M5": 5, "M6": 6, "M8": 8, "M10": 10, "M12": 12,
    "M14": 14, "M16": 16, "M18": 18, "M20": 20, "M22": 22, "M24": 24,
    "M27": 27, "M30": 30,
}

#: Strength grade for a bolt or screw, or the stainless designation.
PROPERTY_CLASSES = ["4.8", "5.8", "8.8", "10.9", "12.9", "A2-70", "A4-80"]

#: Nuts are not graded like bolts. ISO 898-2 gives a nut a single number, and
#: a nut must be at least as strong as the bolt it is used with, so a "class
#: 8.8 nut" is a line that has to be queried rather than quietly matched.
NUT_PROPERTY_CLASSES = ["04", "05", "6", "8", "10", "12", "A2-70", "A4-80"]

#: Washers are specified by hardness, not by strength class (ISO 7089 200 HV).
WASHER_HARDNESS_CLASSES = ["140HV", "200HV", "300HV", "A2-70", "A4-80"]

#: Surface finish. The spoken name on the left, the catalogue code on the right.
FINISH_SYNONYMS: dict[str, str] = {
    "plain": "plain",
    "black": "black_oxide",
    "black oxide": "black_oxide",
    "self colour": "plain",
    "self color": "plain",
    "zinc": "zinc_blue",
    "zinc plated": "zinc_blue",
    "zinc-plated": "zinc_blue",
    "zn": "zinc_blue",
    "blue zinc": "zinc_blue",
    "zinc blue": "zinc_blue",
    "a2k": "zinc_blue",             # Wuerth code: zinc plated, blue passivated
    "clear zinc": "zinc_blue",
    "yellow zinc": "zinc_yellow",
    "zinc yellow": "zinc_yellow",
    "a3c": "zinc_yellow",
    "hot dip": "hot_dip_galvanised",
    "hot dip galvanised": "hot_dip_galvanised",
    "hot dip galvanized": "hot_dip_galvanised",
    "hdg": "hot_dip_galvanised",
    "geomet": "zinc_flake",
    "zinc flake": "zinc_flake",
    "dacromet": "zinc_flake",
    # "zinc plated, blue passivated" is one finish, not two. The phrase is
    # listed in full so the two halves are not read as a clash.
    "blue passivated": "zinc_blue",
    "yellow passivated": "zinc_yellow",
    "stainless": "stainless_plain",
    "bare stainless": "stainless_plain",
}

FINISH_DISPLAY: dict[str, str] = {
    "plain": "plain (self colour)",
    "black_oxide": "black oxide",
    "zinc_blue": "zinc plated, blue passivated",
    "zinc_yellow": "zinc plated, yellow passivated",
    "hot_dip_galvanised": "hot dip galvanised",
    "zinc_flake": "zinc flake coated",
    "stainless_plain": "stainless, untreated",
}

#: Coatings that cannot be applied to stainless steel.
PLATED_FINISHES = {"zinc_blue", "zinc_yellow", "hot_dip_galvanised", "zinc_flake"}

#: Finishes grouped by what they actually are. "Zinc plated, yellow
#: passivated" names one finish in two ways, so the two readings reinforce
#: each other; "zinc plated, hot dip galvanised" names two, and that is a
#: genuine contradiction worth asking about.
FINISH_FAMILY: dict[str, str] = {
    "plain": "bare",
    "black_oxide": "bare",
    "zinc_blue": "zinc",
    "zinc_yellow": "zinc",
    "zinc_flake": "zinc",
    "hot_dip_galvanised": "galvanised",
    "stainless_plain": "stainless",
}

#: Materials that cannot carry a steel strength class, and the other way round.
STAINLESS_CLASSES = {"A2-70", "A4-80"}

#: Bearing seal and shield suffixes by brand. ISO 15 fixes the dimensions, so a
#: cross-reference only has to reconcile these suffixes.
BEARING_SUFFIX_BY_BRAND: dict[str, dict[str, str]] = {
    "SKF": {"open": "", "shielded_both": "-2Z", "sealed_both": "-2RS1", "sealed_one": "-RS1"},
    "FAG": {"open": "", "shielded_both": ".2ZR", "sealed_both": ".2RSR", "sealed_one": ".RSR"},
    "NSK": {"open": "", "shielded_both": "ZZ", "sealed_both": "DDU", "sealed_one": "DU"},
    "NTN": {"open": "", "shielded_both": "ZZ", "sealed_both": "LLU", "sealed_one": "LU"},
    "Timken": {"open": "", "shielded_both": "-2Z", "sealed_both": "-2RS", "sealed_one": "-RS"},
    "Koyo": {"open": "", "shielded_both": "ZZ", "sealed_both": "2RS", "sealed_one": "RS"},
}

#: Normalised seal wording the matcher understands, in order of how specific it is.
BEARING_SEAL_TOKENS: list[tuple[str, str]] = [
    ("2RS1", "sealed_both"), ("2RSR", "sealed_both"), ("2RSH", "sealed_both"),
    ("2RSL", "sealed_both"), ("DDU", "sealed_both"), ("LLU", "sealed_both"),
    ("2RS", "sealed_both"), ("VV", "sealed_both"),
    ("2ZR", "shielded_both"), ("2Z", "shielded_both"), ("ZZ", "shielded_both"),
    ("RSR", "sealed_one"), ("RS1", "sealed_one"), ("RS", "sealed_one"),
    ("LU", "sealed_one"), ("DU", "sealed_one"), ("Z", "shielded_one"),
]

#: Deep groove ball bearing geometry from ISO 15, bore series 00-20 and the
#: 6000 / 6200 / 6300 light-to-heavy width series. Bore, outside, width in mm.
BEARING_GEOMETRY: dict[str, tuple[int, int, int]] = {
    "6000": (10, 26, 8), "6001": (12, 28, 8), "6002": (15, 32, 9),
    "6003": (17, 35, 10), "6004": (20, 42, 12), "6005": (25, 47, 12),
    "6006": (30, 55, 13), "6007": (35, 62, 14), "6008": (40, 68, 15),
    "6200": (10, 30, 9), "6201": (12, 32, 10), "6202": (15, 35, 11),
    "6203": (17, 40, 12), "6204": (20, 47, 14), "6205": (25, 52, 15),
    "6206": (30, 62, 16), "6207": (35, 72, 17), "6208": (40, 80, 18),
    "6300": (10, 35, 11), "6301": (12, 37, 12), "6302": (15, 42, 13),
    "6303": (17, 47, 14), "6304": (20, 52, 15), "6305": (25, 62, 17),
    "6306": (30, 72, 19), "6307": (35, 80, 21), "6308": (40, 90, 23),
}

BEARING_CLEARANCES = ["C2", "CN", "C3", "C4"]


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
_PUNCT = re.compile(r"[^A-Z0-9]+")


def normalise_number(value: str) -> str:
    """Strip everything a human might vary: case, dashes, dots, spaces.

    ``skf 6204-2RS1`` and ``SKF6204 2RS1`` both become ``SKF62042RS1``.
    """
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value).upper()
    return _PUNCT.sub("", text)


def normalise_text(value: str) -> str:
    """Lower case, collapse whitespace, unify the characters people mix up."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = text.replace("×", "x").replace("ｘ", "x").replace("*", "x")
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    return re.sub(r"\s+", " ", text).strip().lower()


def canonical_standard(value: str) -> str:
    """Return the ISO name when a DIN name was used, so both match one part."""
    key = re.sub(r"\s+", " ", (value or "").upper().replace("-", " ")).strip()
    return EQUIVALENT_STANDARDS.get(key, key)


# ---------------------------------------------------------------------------
# Parsed result
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class ParsedSpecification:
    """What a line of a request for quote actually asks for."""

    family: str = ""                       # fastener | bearing | pneumatic | unknown
    attributes: dict[str, Any] = field(default_factory=dict)
    standard: str = ""
    brand: str = ""
    external_number: str = ""
    conflicts: list[dict[str, str]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    #: Attributes the agent filled in itself rather than read off the line. A
    #: disagreement on one of these lowers confidence; a disagreement on an
    #: attribute the customer actually wrote rejects the candidate outright.
    assumed: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return not self.missing and not self.conflicts

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "standard": self.standard,
            "brand": self.brand,
            "external_number": self.external_number,
            "attributes": self.attributes,
            "conflicts": self.conflicts,
            "missing": self.missing,
            "notes": self.notes,
            "assumed": self.assumed,
        }


#: Attributes a line must state before it can be priced, per family.
REQUIRED_ATTRIBUTES: dict[str, list[str]] = {
    "fastener": ["kind", "thread", "length_mm", "property_class", "finish"],
    "bearing": ["designation", "seal"],
    "pneumatic": ["kind", "bore_mm"],
}

#: Nuts and washers have no length, so the requirement is relaxed for them.
NO_LENGTH_KINDS = {
    "hex_nut", "prevailing_torque_nut", "lock_nut", "flat_washer", "spring_washer",
}


# ---------------------------------------------------------------------------
# Fasteners
# ---------------------------------------------------------------------------
_STANDARD_RE = re.compile(r"\b(din|iso)[\s\-]?(\d{3,5})\b", re.I)

#: Thread diameter on its own. Written as one assertion rather than one
#: expression with an optional pitch group, because a single expression
#: backtracks and silently fails on the most ordinary form of all, M18x90.
_THREAD_RE = re.compile(r"(?<![a-z0-9])m\s*(\d{1,2})(?![0-9])", re.I)

#: A fine pitch immediately after the thread, always written with a decimal
#: point: M8-1.25, M12x1.5. An integer in that position is the length.
_PITCH_AFTER_THREAD_RE = re.compile(r"^\s*[x×*\-]\s*(\d\.\d{1,2})")

#: The length, immediately after the thread or its pitch.
_LENGTH_AFTER_THREAD_RE = re.compile(r"^\s*[x×*\-]\s*(\d{1,4})(?![\d.])")

#: A length stated further along the line, as in "M10 socket screw x 40 mm".
_LENGTH_ANYWHERE_RE = re.compile(r"[x×*]\s*(\d{1,3})\s*(?:mm)?(?![\d.])", re.I)
_CLASS_RE = re.compile(r"\b(?:cl\.?|class|grade|gr\.?|property\s+class)?\s?(4\.8|5\.8|8\.8|10\.9|12\.9)\b", re.I)
_STAINLESS_RE = re.compile(r"\b(a2[\s\-]?70|a4[\s\-]?80|a2|a4|304|316|ss)\b", re.I)

#: A nut class is a bare number, so it is only read when the line says so.
_NUT_CLASS_RE = re.compile(r"\b(?:cl\.?|class|grade|gr\.?|property\s+class)\s*(0?4|0?5|6|8|10|12)\b", re.I)

#: Washer hardness, written as 200 HV.
_HARDNESS_RE = re.compile(r"\b(\d{3})\s*hv\b", re.I)

#: Words that say "this is a threaded fastener" without saying which kind.
_GENERIC_FASTENER_RE = re.compile(r"\b(bolt|screw|stud|nut|washer|fastener)s?\b", re.I)


def _detect_finish(text: str) -> tuple[str, list[str]]:
    """Return the finish code and every finish genuinely named on the line.

    Longest phrase first, and each match is blanked out before the next phrase
    is tried. Without that, "yellow zinc" also matches the bare word "zinc" and
    the line looks as though it names two different finishes.
    """
    remaining = text
    found: list[str] = []
    for phrase, code in sorted(FINISH_SYNONYMS.items(), key=lambda kv: -len(kv[0])):
        pattern = re.compile(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])")
        match = pattern.search(remaining)
        if match:
            remaining = remaining[: match.start()] + " " * (match.end() - match.start()) + remaining[match.end():]
            if code not in found:
                found.append(code)
    return (found[0] if found else ""), found


def parse_fastener(text: str) -> ParsedSpecification | None:
    low = normalise_text(text)
    spec = ParsedSpecification(family="fastener")

    standard_match = _STANDARD_RE.search(low)
    kind = ""
    if standard_match:
        raw = f"{standard_match.group(1).upper()} {standard_match.group(2)}"
        spec.standard = canonical_standard(raw)
        definition = FASTENER_STANDARDS.get(raw.upper()) or FASTENER_STANDARDS.get(spec.standard)
        if definition:
            kind = definition["kind"]
            spec.attributes.update({k: v for k, v in definition.items() if k != "kind"})
        else:
            spec.notes.append(f"Standard {raw} is not in the catalogue of standards we stock.")

    # Spoken descriptions, used when no standard number is given.
    if not kind:
        for words, value in [
            (("socket head cap", "shcs", "socket cap", "allen bolt", "cap screw"), "socket_head_cap_screw"),
            (("button head",), "button_head_screw"),
            (("countersunk", "flat head socket"), "countersunk_socket_screw"),
            (("partially threaded", "part thread", "half thread"), "hex_head_bolt_partial"),
            (("hex bolt", "hexagon bolt", "hex head", "hex set screw"), "hex_head_bolt"),
            (("set screw", "grub screw", "socket set"), "socket_set_screw"),
            (("threaded stud", "stud bolt", "threaded rod", "all thread"), "threaded_stud"),
            (("nyloc", "nylon insert", "prevailing torque", "lock nut", "locknut"),
             "prevailing_torque_nut"),
            (("hex nut", "hexagon nut", "nut"), "hex_nut"),
            (("spring washer", "lock washer"), "spring_washer"),
            (("flat washer", "plain washer", "washer"), "flat_washer"),
        ]:
            if any(w in low for w in words):
                kind = value
                break

    if not kind:
        # "M10 bolt, class 8.8, zinc" is unmistakably a threaded fastener and
        # unmistakably underspecified. It is read as a fastener with the type
        # missing, which produces a question, rather than being thrown away as
        # something we could not read at all.
        # A line that names a published standard Hengtai does not stock is not
        # an underspecified fastener; it is a part to ask a supplier about. It
        # is handed back unread so the matcher treats it that way.
        if standard_match and not FASTENER_STANDARDS.get(
            f"{standard_match.group(1).upper()} {standard_match.group(2)}"
        ):
            return None
        if _GENERIC_FASTENER_RE.search(low) and _THREAD_RE.search(low):
            spec.missing.append("kind")
            spec.notes.append(
                "The line names a threaded fastener but not which type, so the type "
                "has to be confirmed."
            )
        else:
            return None
    else:
        spec.attributes["kind"] = kind

    thread_match = _THREAD_RE.search(low)
    tail = ""
    if thread_match:
        thread = f"M{int(thread_match.group(1))}"
        spec.attributes["thread"] = thread
        tail = low[thread_match.end():]

        pitch_match = _PITCH_AFTER_THREAD_RE.match(tail)
        if pitch_match:
            spec.attributes["pitch_mm"] = pitch_match.group(1)
            spec.attributes["pitch_kind"] = (
                "coarse" if pitch_match.group(1) == COARSE_PITCH.get(thread) else "fine"
            )
            tail = tail[pitch_match.end():]
        else:
            spec.attributes["pitch_mm"] = COARSE_PITCH.get(thread, "")
            spec.attributes["pitch_kind"] = "coarse"
            spec.assumed.append("pitch_mm")
    else:
        spec.missing.append("thread")

    if kind not in NO_LENGTH_KINDS:
        # The length is whatever follows the thread, and its pitch if one was
        # written. A number anywhere else on the line is not a length.
        length_match = _LENGTH_AFTER_THREAD_RE.match(tail) or _LENGTH_ANYWHERE_RE.search(tail)
        if length_match:
            spec.attributes["length_mm"] = str(int(length_match.group(1)))
        else:
            spec.missing.append("length_mm")

    stainless_match = _STAINLESS_RE.search(low)
    class_match = _CLASS_RE.search(low)

    # A nut is graded 6, 8, 10 or 12 under ISO 898-2, and a washer by hardness
    # under ISO 7089. Reading a bolt class onto either of them is how the wrong
    # part gets quoted, so each kind is read with its own rule.
    if kind == "hex_nut" and not stainless_match:
        nut_match = _NUT_CLASS_RE.search(low)
        if class_match:
            spec.conflicts.append(
                {
                    "attribute": "property_class",
                    "values": f"nut with bolt class {class_match.group(1)}",
                    "explanation": (
                        "Nuts are graded 6, 8, 10 or 12 under ISO 898-2, not with a "
                        "bolt class such as " + class_match.group(1) + "."
                    ),
                }
            )
        elif nut_match:
            spec.attributes["property_class"] = nut_match.group(1).lstrip("0") or "4"
            spec.attributes["material"] = "carbon_steel"
        else:
            spec.missing.append("property_class")
        _finish_and_return(spec, low)
        return spec

    if kind == "flat_washer" and not stainless_match:
        hardness_match = _HARDNESS_RE.search(low)
        if hardness_match:
            spec.attributes["property_class"] = f"{hardness_match.group(1)}HV"
            spec.attributes["material"] = "carbon_steel"
        else:
            spec.missing.append("property_class")
        _finish_and_return(spec, low)
        return spec

    if stainless_match and class_match:
        spec.conflicts.append(
            {
                "attribute": "property_class",
                "values": f"{stainless_match.group(1)} and {class_match.group(1)}",
                "explanation": (
                    "Stainless steel does not carry a steel strength class such as "
                    f"{class_match.group(1)}. Please confirm which one applies."
                ),
            }
        )
    elif stainless_match:
        token = stainless_match.group(1).replace(" ", "").replace("-", "").upper()
        mapping = {"A270": "A2-70", "A480": "A4-80", "A2": "A2-70", "A4": "A4-80",
                   "304": "A2-70", "316": "A4-80", "SS": "A2-70"}
        spec.attributes["property_class"] = mapping.get(token, "A2-70")
        spec.attributes["material"] = "stainless_steel"
        if token in {"SS", "A2", "A4"}:
            spec.notes.append(
                "Stainless grade read as " + mapping.get(token, "A2-70") + " from a short form."
            )
    elif class_match:
        spec.attributes["property_class"] = class_match.group(1)
        spec.attributes["material"] = "carbon_steel"
    else:
        spec.missing.append("property_class")

    _finish_and_return(spec, low)
    return spec


def _finish_and_return(spec: ParsedSpecification, low: str) -> None:
    """Read the surface finish and check it against the material.

    At most one question comes out of this, and when stainless steel is named
    alongside a plating that is the question worth asking, because it is the
    one a person can answer without going back to the drawing.
    """
    finish, all_finishes = _detect_finish(low)
    families = list(dict.fromkeys(FINISH_FAMILY.get(f, f) for f in all_finishes))
    stainless = spec.attributes.get("material") == "stainless_steel" or (
        "stainless_plain" in all_finishes
    )
    plating = next((f for f in all_finishes if f in PLATED_FINISHES), "")

    if stainless and plating:
        spec.conflicts.append(
            {
                "attribute": "finish",
                "values": f"stainless steel and {FINISH_DISPLAY.get(plating, plating)}",
                "explanation": (
                    "Stainless steel is not plated, so the line cannot be both. "
                    "Please confirm the material or the finish."
                ),
            }
        )
        return

    if len(families) > 1:
        spec.conflicts.append(
            {
                "attribute": "finish",
                "values": ", ".join(FINISH_DISPLAY.get(f, f) for f in all_finishes),
                "explanation": "More than one surface finish is named for the same line.",
            }
        )
    elif finish:
        # Within one family the most specific wording wins, and the phrases are
        # tried longest first, so "yellow passivated" beats the bare "zinc".
        spec.attributes["finish"] = finish
    else:
        spec.missing.append("finish")


# ---------------------------------------------------------------------------
# Bearings
# ---------------------------------------------------------------------------
# A bearing number is often written with its seal suffix joined on, as in
# 6001LLU, so a trailing word boundary would miss it.
_BEARING_RE = re.compile(r"(?<![0-9a-z])(6[0-3]\d{2})(?![0-9])")
_CLEARANCE_RE = re.compile(r"\b(c2|cn|c3|c4)\b", re.I)
_BEARING_BRAND_RE = re.compile(r"\b(skf|fag|nsk|ntn|timken|koyo|nachi)\b", re.I)


def parse_bearing(text: str) -> ParsedSpecification | None:
    low = normalise_text(text)
    match = _BEARING_RE.search(low)
    if not match:
        return None

    designation = match.group(1)
    spec = ParsedSpecification(family="bearing", standard="ISO 15")
    spec.attributes["designation"] = designation

    geometry = BEARING_GEOMETRY.get(designation)
    if geometry:
        bore, outside, width = geometry
        spec.attributes.update(
            {"bore_mm": str(bore), "outside_diameter_mm": str(outside), "width_mm": str(width)}
        )
        spec.notes.append(
            f"ISO 15 fixes {designation} at {bore} x {outside} x {width} mm for every maker."
        )
    else:
        spec.notes.append(f"{designation} is not a size Hengtai stocks.")

    brand_match = _BEARING_BRAND_RE.search(low)
    if brand_match:
        spec.brand = brand_match.group(1).upper() if brand_match.group(1).lower() != "timken" else "Timken"
        if spec.brand == "KOYO":
            spec.brand = "Koyo"
        if spec.brand == "NACHI":
            spec.brand = "Nachi"

    # Seal suffix. Longest token first so 2RS1 is not read as RS1.
    after = low[match.end():].upper().replace(" ", "").replace("-", "").replace(".", "")
    seal = ""
    for token, value in BEARING_SEAL_TOKENS:
        if after.startswith(token) or token in after[:6]:
            seal = value
            spec.attributes["seal_suffix_seen"] = token
            break
    if seal:
        spec.attributes["seal"] = seal
    elif re.search(r"\bopen\b", low):
        spec.attributes["seal"] = "open"
    else:
        # Silence is not the same as "open". A bearing quoted without its
        # sealing is the single most common way to ship the wrong part.
        spec.missing.append("seal")

    clearance_match = _CLEARANCE_RE.search(low)
    if clearance_match:
        spec.attributes["clearance"] = clearance_match.group(1).upper()
    else:
        spec.attributes["clearance"] = "CN"
        spec.assumed.append("clearance")
        spec.notes.append("No internal clearance stated, so normal clearance CN is assumed.")

    spec.external_number = (spec.brand + " " + designation).strip() if spec.brand else designation
    return spec


# ---------------------------------------------------------------------------
# Pneumatic parts
# ---------------------------------------------------------------------------
_BORE_RE = re.compile(r"\b(?:bore|dia(?:meter)?)\s*[:=]?\s*(\d{2,3})\b|\b(\d{2,3})\s*mm\s*bore\b", re.I)
_STROKE_RE = re.compile(r"\b(?:stroke)\s*[:=]?\s*(\d{1,4})\b|\b(\d{1,4})\s*mm\s*stroke\b", re.I)
_PORT_RE = re.compile(r"\b(g\s?1/[248]|g\s?[13]/[48]|rc\s?1/[248]|m5)\b", re.I)


def parse_pneumatic(text: str) -> ParsedSpecification | None:
    low = normalise_text(text)
    kind = ""
    if "15552" in low or "iso cylinder" in low or ("cylinder" in low and "pneumatic" in low):
        kind = "iso_15552_cylinder"
    elif "compact cylinder" in low:
        kind = "compact_cylinder"
    elif "solenoid valve" in low or "5/2" in low or "3/2" in low:
        kind = "solenoid_valve"
    elif "push-in fitting" in low or "push in fitting" in low or "one touch fitting" in low:
        kind = "push_in_fitting"
    elif "air cylinder" in low:
        kind = "iso_15552_cylinder"
    if not kind:
        return None

    spec = ParsedSpecification(family="pneumatic")
    spec.attributes["kind"] = kind
    if kind == "iso_15552_cylinder":
        spec.standard = "ISO 15552"

    bore_match = _BORE_RE.search(low)
    if bore_match:
        spec.attributes["bore_mm"] = bore_match.group(1) or bore_match.group(2)
    elif kind in {"iso_15552_cylinder", "compact_cylinder"}:
        spec.missing.append("bore_mm")

    stroke_match = _STROKE_RE.search(low)
    if stroke_match:
        spec.attributes["stroke_mm"] = stroke_match.group(1) or stroke_match.group(2)
    elif kind in {"iso_15552_cylinder", "compact_cylinder"}:
        spec.missing.append("stroke_mm")

    port_match = _PORT_RE.search(low)
    if port_match:
        spec.attributes["port"] = port_match.group(1).upper().replace(" ", "")

    if "double acting" in low:
        spec.attributes["action"] = "double_acting"
    elif "single acting" in low:
        spec.attributes["action"] = "single_acting"
    elif kind in {"iso_15552_cylinder", "compact_cylinder"}:
        spec.attributes["action"] = "double_acting"
        spec.assumed.append("action")
        spec.notes.append("No action stated, so double acting is assumed.")

    return spec


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def parse_specification(text: str) -> ParsedSpecification:
    """Read one request line into attributes, with what is missing or clashing."""
    for parser in (parse_bearing, parse_fastener, parse_pneumatic):
        result = parser(text)
        if result is not None:
            result.missing = [m for m in result.missing if m]
            return result

    spec = ParsedSpecification(family="unknown")
    standard_match = _STANDARD_RE.search(normalise_text(text))
    if standard_match:
        named = f"{standard_match.group(1).upper()} {standard_match.group(2)}"
        spec.standard = canonical_standard(named)
        spec.notes.append(
            f"The line is written to {named}, which is a published standard Hengtai "
            "does not stock. It has to be priced by a supplier."
        )
    else:
        spec.notes.append(
            "The line does not read as a fastener, a bearing or a pneumatic part."
        )
    return spec


def merge_specifications(
    primary: ParsedSpecification, secondary: ParsedSpecification
) -> ParsedSpecification:
    """Combine two readings of the same line, for example an email line and the
    matching spreadsheet row, and record every place they disagree."""
    merged = ParsedSpecification(
        family=(
            primary.family
            if primary.family and primary.family != "unknown"
            else secondary.family
        ),
        standard=primary.standard or secondary.standard,
        brand=primary.brand or secondary.brand,
        external_number=primary.external_number or secondary.external_number,
    )
    merged.attributes = dict(secondary.attributes)
    merged.notes = list(dict.fromkeys(primary.notes + secondary.notes))
    merged.conflicts = list(primary.conflicts) + list(secondary.conflicts)
    merged.assumed = [
        attribute
        for attribute in dict.fromkeys(primary.assumed + secondary.assumed)
        if attribute not in primary.attributes or attribute in primary.assumed
    ]

    for key, value in primary.attributes.items():
        other = secondary.attributes.get(key)
        if other not in (None, "", value) and key not in {"seal_suffix_seen", "pitch_kind"}:
            merged.conflicts.append(
                {
                    "attribute": key,
                    "values": f"{value} and {other}",
                    "explanation": (
                        f"The written request says {value} for {key.replace('_', ' ')} "
                        f"while the attachment says {other}."
                    ),
                }
            )
        merged.attributes[key] = value

    required = REQUIRED_ATTRIBUTES.get(merged.family, [])
    kind = merged.attributes.get("kind", "")
    merged.missing = [
        attribute
        for attribute in required
        if not merged.attributes.get(attribute)
        and not (attribute == "length_mm" and kind in NO_LENGTH_KINDS)
    ]
    return merged


def describe_attribute(name: str, value: Any) -> str:
    """Plain words for the interface. No codes, no abbreviations."""
    labels = {
        "kind": "part type",
        "thread": "thread size",
        "pitch_mm": "thread pitch in millimetres",
        "length_mm": "length in millimetres",
        "property_class": "strength class",
        "material": "material",
        "finish": "surface finish",
        "designation": "bearing number",
        "seal": "sealing",
        "clearance": "internal clearance",
        "bore_mm": "bore in millimetres",
        "stroke_mm": "stroke in millimetres",
        "outside_diameter_mm": "outside diameter in millimetres",
        "width_mm": "width in millimetres",
        "port": "port thread",
        "action": "action",
    }
    values = {
        "socket_head_cap_screw": "socket head cap screw",
        "hex_head_bolt": "hexagon head bolt, fully threaded",
        "hex_head_bolt_partial": "hexagon head bolt, partially threaded",
        "hex_nut": "hexagon nut",
        "flat_washer": "flat washer",
        "button_head_screw": "button head screw",
        "countersunk_socket_screw": "countersunk socket screw",
        "socket_set_screw": "socket set screw",
        "threaded_stud": "threaded stud",
        "prevailing_torque_nut": "prevailing torque nut with a nylon insert",
        "spring_washer": "spring lock washer",
        "iso_15552_cylinder": "pneumatic cylinder to ISO 15552",
        "compact_cylinder": "compact pneumatic cylinder",
        "solenoid_valve": "solenoid valve",
        "push_in_fitting": "push-in fitting",
        "sealed_both": "sealed both sides",
        "sealed_one": "sealed one side",
        "shielded_both": "shielded both sides",
        "shielded_one": "shielded one side",
        "open": "open, no seal",
        "carbon_steel": "carbon steel",
        "stainless_steel": "stainless steel",
        "double_acting": "double acting",
        "single_acting": "single acting",
    }
    label = labels.get(name, name.replace("_", " "))
    shown = FINISH_DISPLAY.get(str(value)) or values.get(str(value)) or str(value)
    return f"{label}: {shown}"
