"""Units, pack sizes and minimum order quantities.

Customers ask in pieces. Hengtai sells fasteners in boxes of 100 or 500, and a
supplier will not make fewer than 2,000 of a non-stocked part. Getting this
wrong is the quiet way a quote loses money, so it is done by code and the
rounding is always shown on the quote.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal

from ..money import TraceInput, dec

#: Spelling people use -> the unit we store.
UNIT_SYNONYMS: dict[str, str] = {
    "pc": "piece", "pcs": "piece", "piece": "piece", "pieces": "piece",
    "ea": "piece", "each": "piece", "unit": "piece", "units": "piece",
    "nos": "piece", "no": "piece", "支": "piece", "個": "piece", "件": "piece",
    "box": "box", "boxes": "box", "bx": "box", "盒": "box",
    "pack": "box", "packet": "box", "pkt": "box",
    "set": "set", "sets": "set", "組": "set",
    "k": "thousand", "m": "thousand",   # "10 M bolts" means ten thousand in the trade
    "thousand": "thousand",
    "kg": "kilogram", "kgs": "kilogram", "kilogram": "kilogram", "公斤": "kilogram",
}

UNIT_DISPLAY: dict[str, str] = {
    "piece": "pieces",
    "box": "boxes",
    "set": "sets",
    "thousand": "thousands",
    "kilogram": "kilograms",
}

#: Units we can convert into pieces without knowing the part.
PIECE_FACTORS: dict[str, int] = {"piece": 1, "thousand": 1000}


class UnitError(ValueError):
    """Raised when a unit cannot be turned into pieces without asking."""


def canonical_unit(unit: str) -> str:
    key = (unit or "").strip().lower().rstrip(".")
    return UNIT_SYNONYMS.get(key, key or "piece")


def display_unit(unit: str, quantity: Decimal | int | None = None) -> str:
    base = UNIT_DISPLAY.get(canonical_unit(unit), canonical_unit(unit))
    if quantity is not None and dec(quantity) == 1:
        return base.rstrip("s") if base.endswith("es") is False else base
    return base


def to_pieces(quantity: Decimal | int | str, unit: str, pack_size: int) -> Decimal:
    """Convert a requested quantity into pieces."""
    unit = canonical_unit(unit)
    amount = dec(quantity)
    if unit in PIECE_FACTORS:
        return amount * PIECE_FACTORS[unit]
    if unit in {"box", "set"}:
        if pack_size <= 0:
            raise UnitError("This part has no pack size recorded, so boxes cannot be converted.")
        return amount * pack_size
    if unit == "kilogram":
        raise UnitError(
            "Quantity is given by weight. Hengtai sells this part by the piece, "
            "so the number of pieces has to be confirmed."
        )
    raise UnitError(f"Unit {unit!r} is not one the pricing engine can convert.")


def round_up_to_multiple(quantity: Decimal, multiple: int) -> Decimal:
    if multiple <= 1:
        return dec(quantity).to_integral_value(rounding=ROUND_CEILING)
    steps = (dec(quantity) / dec(multiple)).to_integral_value(rounding=ROUND_CEILING)
    return steps * dec(multiple)


class QuantityPlan:
    """The result of turning a request into something Hengtai can actually sell."""

    __slots__ = (
        "requested_quantity",
        "requested_unit",
        "pieces_requested",
        "pieces_billed",
        "pack_size",
        "minimum_order_quantity",
        "boxes",
        "unit_of_sale",
        "notes",
        "trace_inputs",
    )

    def __init__(
        self,
        requested_quantity: Decimal,
        requested_unit: str,
        pieces_requested: Decimal,
        pieces_billed: Decimal,
        pack_size: int,
        minimum_order_quantity: int,
        unit_of_sale: str,
        notes: list[str],
        trace_inputs: list[TraceInput],
    ) -> None:
        self.requested_quantity = requested_quantity
        self.requested_unit = requested_unit
        self.pieces_requested = pieces_requested
        self.pieces_billed = pieces_billed
        self.pack_size = pack_size
        self.minimum_order_quantity = minimum_order_quantity
        self.boxes = (pieces_billed / dec(pack_size)) if pack_size > 1 else pieces_billed
        self.unit_of_sale = unit_of_sale
        self.notes = notes
        self.trace_inputs = trace_inputs

    @property
    def was_rounded(self) -> bool:
        return self.pieces_billed != self.pieces_requested

    @property
    def rounding_note(self) -> str:
        return " ".join(self.notes)

    def to_dict(self) -> dict[str, object]:
        return {
            "requested_quantity": str(self.requested_quantity),
            "requested_unit": self.requested_unit,
            "pieces_requested": str(self.pieces_requested),
            "pieces_billed": str(self.pieces_billed),
            "pack_size": self.pack_size,
            "minimum_order_quantity": self.minimum_order_quantity,
            "boxes": str(self.boxes),
            "unit_of_sale": self.unit_of_sale,
            "was_rounded": self.was_rounded,
            "notes": self.notes,
        }


def plan_quantity(
    *,
    requested_quantity: Decimal | int | str,
    requested_unit: str,
    pack_size: int,
    minimum_order_quantity: int = 1,
    is_stocked: bool = True,
    product_label: str = "",
) -> QuantityPlan:
    """Work out how many pieces will actually be billed, and say why.

    Order of operations, which matters: convert to pieces, then raise to the
    supplier minimum if the part is not stocked, then round up to a whole
    number of boxes. Rounding last means the customer is never billed for a
    part box.
    """
    unit = canonical_unit(requested_unit)
    requested = dec(requested_quantity)
    pack_size = max(int(pack_size or 1), 1)
    minimum_order_quantity = max(int(minimum_order_quantity or 1), 1)

    pieces = to_pieces(requested, unit, pack_size)
    notes: list[str] = []
    inputs = [
        TraceInput("Quantity asked for", f"{requested} {display_unit(unit, requested)}",
                   "Customer request", "request"),
        TraceInput("Pack size", f"{pack_size} pieces per box", product_label, "catalogue"),
    ]

    if unit != "piece":
        notes.append(
            f"{requested} {display_unit(unit, requested)} is {pieces} pieces."
        )

    billed = pieces
    if not is_stocked and minimum_order_quantity > 1 and billed < minimum_order_quantity:
        notes.append(
            f"The supplier will not make fewer than {minimum_order_quantity} pieces, "
            f"so the quantity is raised from {billed} to {minimum_order_quantity}."
        )
        billed = dec(minimum_order_quantity)
        inputs.append(
            TraceInput("Supplier minimum", f"{minimum_order_quantity} pieces",
                       product_label, "catalogue")
        )

    if pack_size > 1:
        rounded = round_up_to_multiple(billed, pack_size)
        if rounded != billed:
            notes.append(
                f"Sold in boxes of {pack_size}, so {billed} pieces is rounded up to "
                f"{rounded} pieces, which is {int(rounded / pack_size)} boxes."
            )
        billed = rounded
    else:
        billed = billed.to_integral_value(rounding=ROUND_CEILING)

    unit_of_sale = "box" if pack_size > 1 else "piece"
    return QuantityPlan(
        requested_quantity=requested,
        requested_unit=unit,
        pieces_requested=pieces,
        pieces_billed=billed,
        pack_size=pack_size,
        minimum_order_quantity=minimum_order_quantity,
        unit_of_sale=unit_of_sale,
        notes=notes,
        trace_inputs=inputs,
    )
