"""Incoterms 2020: who pays for what.

The eleven rules of Incoterms 2020 decide whether a quoted price has to carry
export clearance, main carriage, insurance, delivery at destination and import
duty. Quoting DDP and forgetting the duty is a direct hit to margin, so the
rule set is data, not something anybody has to remember.

Seven rules apply to any mode of transport (EXW, FCA, CPT, CIP, DAP, DPU, DDP)
and four apply only to sea and inland waterway (FAS, FOB, CFR, CIF).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IncotermRule:
    code: str
    name: str
    transport: str              # any_mode | sea_and_inland_waterway
    seller_pays_export_clearance: bool
    seller_pays_origin_handling: bool
    seller_pays_main_carriage: bool
    seller_pays_insurance: bool
    seller_pays_destination_delivery: bool
    seller_pays_import_duty: bool
    risk_passes: str

    @property
    def needs_named_place(self) -> bool:
        return True

    def cost_components(self) -> list[str]:
        """The cost lines the quote has to include for this rule."""
        parts = ["goods"]
        if self.seller_pays_export_clearance or self.seller_pays_origin_handling:
            parts.append("origin charges")
        if self.seller_pays_main_carriage:
            parts.append("main carriage")
        if self.seller_pays_insurance:
            parts.append("insurance")
        if self.seller_pays_destination_delivery:
            parts.append("delivery at destination")
        if self.seller_pays_import_duty:
            parts.append("import duty and import taxes")
        return parts

    def plain_summary(self) -> str:
        return (
            f"{self.name} at the named place. The price Hengtai quotes covers "
            + ", ".join(self.cost_components())
            + f". Risk passes to the buyer {self.risk_passes}."
        )


INCOTERMS: dict[str, IncotermRule] = {
    "EXW": IncotermRule(
        "EXW", "Ex Works", "any_mode",
        False, False, False, False, False, False,
        "when the goods are placed at the buyer's disposal at the seller's premises",
    ),
    "FCA": IncotermRule(
        "FCA", "Free Carrier", "any_mode",
        True, True, False, False, False, False,
        "when the goods are handed to the carrier the buyer nominated",
    ),
    "CPT": IncotermRule(
        "CPT", "Carriage Paid To", "any_mode",
        True, True, True, False, False, False,
        "when the goods are handed to the first carrier, although the seller pays the freight",
    ),
    "CIP": IncotermRule(
        "CIP", "Carriage and Insurance Paid To", "any_mode",
        True, True, True, True, False, False,
        "when the goods are handed to the first carrier; the seller insures to Institute Cargo Clauses A",
    ),
    "DAP": IncotermRule(
        "DAP", "Delivered at Place", "any_mode",
        True, True, True, False, True, False,
        "when the goods are ready for unloading at the named place",
    ),
    "DPU": IncotermRule(
        "DPU", "Delivered at Place Unloaded", "any_mode",
        True, True, True, False, True, False,
        "when the goods are unloaded at the named place",
    ),
    "DDP": IncotermRule(
        "DDP", "Delivered Duty Paid", "any_mode",
        True, True, True, False, True, True,
        "when the goods, cleared for import, are ready for unloading at the named place",
    ),
    "FAS": IncotermRule(
        "FAS", "Free Alongside Ship", "sea_and_inland_waterway",
        True, True, False, False, False, False,
        "when the goods are placed alongside the vessel at the port of shipment",
    ),
    "FOB": IncotermRule(
        "FOB", "Free on Board", "sea_and_inland_waterway",
        True, True, False, False, False, False,
        "when the goods are on board the vessel at the port of shipment",
    ),
    "CFR": IncotermRule(
        "CFR", "Cost and Freight", "sea_and_inland_waterway",
        True, True, True, False, False, False,
        "when the goods are on board at the port of shipment, although the seller pays the freight",
    ),
    "CIF": IncotermRule(
        "CIF", "Cost, Insurance and Freight", "sea_and_inland_waterway",
        True, True, True, True, False, False,
        "when the goods are on board at the port of shipment; the seller insures to Institute Cargo Clauses C",
    ),
}


class UnknownIncoterm(ValueError):
    pass


def get_incoterm(code: str) -> IncotermRule:
    rule = INCOTERMS.get((code or "").strip().upper())
    if rule is None:
        raise UnknownIncoterm(
            f"{code!r} is not one of the eleven Incoterms 2020 rules: "
            + ", ".join(INCOTERMS)
        )
    return rule


def compare(from_code: str, to_code: str) -> list[str]:
    """Plain sentences describing what changes when the rule changes."""
    before, after = get_incoterm(from_code), get_incoterm(to_code)
    changes: list[str] = []
    checks = [
        ("seller_pays_main_carriage", "the main freight"),
        ("seller_pays_insurance", "cargo insurance"),
        ("seller_pays_destination_delivery", "delivery at the destination"),
        ("seller_pays_import_duty", "import duty and import taxes"),
        ("seller_pays_origin_handling", "origin handling"),
        ("seller_pays_export_clearance", "export clearance"),
    ]
    for field_name, label in checks:
        was, now = getattr(before, field_name), getattr(after, field_name)
        if was != now:
            changes.append(
                f"Hengtai now pays {label}." if now else f"The buyer now pays {label}."
            )
    if not changes:
        changes.append("The costs Hengtai carries do not change between these two rules.")
    return changes
