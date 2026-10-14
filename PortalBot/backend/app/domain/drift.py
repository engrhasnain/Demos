"""Noticing that the portal has changed, before booking a hundred wrong.

The thesis of this whole product.

An automation driving somebody else's screen cannot be made unbreakable.
The screen is not yours; it changes when they ship, and no amount of
cleverness in the selectors makes that untrue. The dominant failure in
this kind of automation is a changed selector, and the usual response —
fuzzy matching, nearest-element, "self-healing" — makes the *expensive*
failure more likely rather than less.

Because stopping is cheap. A bot that stops at nine in the morning costs
one clerk one morning. A bot that carries on against a changed page, puts
the postcode in the weight field and books a hundred and eighty shipments
to the wrong addresses costs a week and a lot of apologising. Self-healing
turns the first failure into the second.

So: the script records the shape of the form it was written against. Every
run checks the shape first. A shape that does not match stops the run and
raises a flag for a developer. **The script is never rewritten by the
machine.** A human reads the diff and changes it, which is the only point
at which anybody can say whether the new field means what the old one did.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field


def fingerprint(fields: list[str]) -> str:
    """A stable hash of a form's shape."""
    return hashlib.sha256("|".join(sorted(fields)).encode()).hexdigest()[:16]


@dataclass(slots=True)
class Expectation:
    """What a script was written against."""

    name: str
    version: str
    fields: list[str]

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.fields)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "fields": self.fields,
            "fingerprint": self.fingerprint,
        }


@dataclass(slots=True)
class Drift:
    """What changed, in terms a developer can act on in a minute."""

    matches: bool
    expected_fingerprint: str
    found_fingerprint: str
    missing: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    #: Pairs that look like a rename rather than a removal and an
    #: addition. Offered to the developer as a suggestion and acted on by
    #: nobody but them.
    looks_renamed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def severity(self) -> str:
        if self.matches:
            return "none"
        if self.missing:
            return "blocking"
        return "note"

    def summary(self) -> str:
        if self.matches:
            return "The form is as the script expects."
        parts = []
        if self.missing:
            parts.append(f"{len(self.missing)} field(s) gone: {', '.join(self.missing)}")
        if self.added:
            parts.append(f"{len(self.added)} new: {', '.join(self.added)}")
        return "; ".join(parts)

    def to_dict(self) -> dict[str, object]:
        return {
            "matches": self.matches,
            "severity": self.severity,
            "expected_fingerprint": self.expected_fingerprint,
            "found_fingerprint": self.found_fingerprint,
            "missing": self.missing,
            "added": self.added,
            "looks_renamed": [list(pair) for pair in self.looks_renamed],
            "summary": self.summary(),
        }


def _tokens(name: str) -> set[str]:
    """``gross_weight_kg`` is three words, not fifteen characters."""
    return {part for part in re.split(r"[_\-\s]+", name.lower()) if part}


def _similar(left: str, right: str) -> float:
    """How alike two field names are.

    Renames in a form come in two shapes and one measure does not catch
    both. ``gross_kg`` to ``gross_weight_kg`` keeps the words and gains
    one, so words find it and characters do not. ``deliver_post`` to
    ``deliver_postcode`` changes a word but keeps almost every character,
    so characters find it and words do not. The score is whichever of the
    two is higher.

    Used only to *suggest* a rename to a person. Nothing acts on it.
    """
    if not left or not right:
        return 0.0

    left_words, right_words = _tokens(left), _tokens(right)
    by_words = (
        len(left_words & right_words) / len(left_words | right_words)
        if left_words and right_words
        else 0.0
    )

    prefix = 0
    for x, y in zip(left.lower(), right.lower()):
        if x != y:
            break
        prefix += 1
    shared = set(left.lower()) & set(right.lower())
    whole = set(left.lower()) | set(right.lower())
    by_characters = (len(shared) / len(whole)) * 0.5 + (
        prefix / max(len(left), len(right))
    ) * 0.5

    return max(by_words, by_characters)


def compare(expected: Expectation, found_fields: list[str]) -> Drift:
    """Has the form moved under the script?"""
    found = sorted(found_fields)
    missing = sorted(set(expected.fields) - set(found))
    added = sorted(set(found) - set(expected.fields))

    renames: list[tuple[str, str]] = []
    for gone in missing:
        best, score = "", 0.0
        for arrived in added:
            value = _similar(gone, arrived)
            if value > score:
                best, score = arrived, value
        if score >= 0.6:
            renames.append((gone, best))

    return Drift(
        matches=not missing and not added,
        expected_fingerprint=expected.fingerprint,
        found_fingerprint=fingerprint(found),
        missing=missing,
        added=added,
        looks_renamed=renames,
    )
