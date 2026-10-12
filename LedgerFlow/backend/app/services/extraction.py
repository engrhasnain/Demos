"""Reading an invoice into fields and lines.

Two engines fill the same strict schema:

* **built-in** — deterministic parsing of the document's text and barcode. No
  key, no account, no network, no cost. This is the default.
* **external** — a hosted model doing the same job, used only when a key is
  configured. Every call is recorded on the invoice timeline with its cost.

Three rules hold whichever engine runs, and none of them is a matter of
prompting:

1. **The engine never decides anything.** It reports what it can read, with a
   confidence per field. Whether the invoice is correct, matched, duplicated
   or payable is settled afterwards by code it cannot reach.
2. **Structured data beats reading.** Where a Taiwan uniform invoice carries a
   square barcode, the barcode is decoded by code and its figures are used as
   the truth, with whatever was read off the page checked against it.
3. **A field it cannot read is marked unread**, never guessed. An unread field
   on a payment document is an exception, not a blank.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from ..config import settings
from ..domain.uniforminvoice import read_barcode
from ..money import dec, money

# ---------------------------------------------------------------------------
# What a reading looks like
# ---------------------------------------------------------------------------
HEADER_FIELDS = (
    "vendor_name",
    "invoice_number",
    "invoice_date",
    "due_date",
    "currency",
    "net_amount",
    "tax_amount",
    "total_amount",
    "buyer_tax_identifier",
    "seller_tax_identifier",
    "purchase_order_number",
    "bank_account",
)


@dataclass(slots=True)
class ReadLine:
    line_number: int
    description: str
    part_code: str = ""
    quantity: Decimal = Decimal("0")
    unit: str = "piece"
    unit_price: Decimal = Decimal("0")
    line_total: Decimal = Decimal("0")
    page: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_number": self.line_number,
            "description": self.description,
            "part_code": self.part_code,
            "quantity": str(self.quantity),
            "unit": self.unit,
            "unit_price": str(self.unit_price),
            "line_total": str(self.line_total),
            "page": self.page,
        }


@dataclass(slots=True)
class Reading:
    header: dict[str, Any] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)
    lines: list[ReadLine] = field(default_factory=list)
    page_subtotals: dict[int, Decimal] = field(default_factory=dict)
    barcode: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)
    engine: str = "built-in"
    duration_ms: int = 0
    cost_usd: Decimal = Decimal("0")
    fell_back: bool = False

    def value(self, name: str) -> Any:
        return self.header.get(name)

    def unread_fields(self, required: tuple[str, ...]) -> list[str]:
        return [name for name in required if not self.header.get(name)]

    def weak_fields(self, floor: float = 0.75) -> list[str]:
        return [
            name
            for name, score in self.confidence.items()
            if score < floor and self.header.get(name)
        ]

    def as_event_detail(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "duration_ms": self.duration_ms,
            "cost_usd": str(self.cost_usd),
            "fields_read": sum(1 for name in HEADER_FIELDS if self.header.get(name)),
            "fields_possible": len(HEADER_FIELDS),
            "lines_read": len(self.lines),
            "pages": len(self.page_subtotals) or 1,
            "barcode_present": self.barcode is not None,
            "notes": self.notes,
            "fell_back_to_built_in": self.fell_back,
        }


# ---------------------------------------------------------------------------
# The built-in engine
# ---------------------------------------------------------------------------
_LABELS: dict[str, tuple[str, ...]] = {
    "vendor_name": ("supplier", "vendor", "from", "seller", "賣方", "供應商"),
    "invoice_number": ("invoice no", "invoice number", "invoice #", "bill no",
                       "發票號碼", "號碼"),
    "invoice_date": ("invoice date", "date", "issued", "開立日期", "日期"),
    "due_date": ("due date", "payment due", "due", "付款期限"),
    "net_amount": ("subtotal", "net", "amount before tax", "sub total",
                   "銷售額", "未稅金額"),
    "tax_amount": ("tax", "vat", "business tax", "營業稅", "稅額"),
    "total_amount": ("total", "grand total", "amount due", "total due",
                     "總計", "合計", "應付金額"),
    "buyer_tax_identifier": ("buyer tax id", "buyer ubn", "customer tax",
                             "買方統一編號", "買方統編"),
    "seller_tax_identifier": ("seller tax id", "seller ubn", "our tax",
                              "賣方統一編號", "賣方統編"),
    "purchase_order_number": ("purchase order", "po number", "po no", "your order",
                              "訂單號碼", "採購單"),
    "bank_account": ("bank account", "account no", "account number", "remit to",
                     "匯款帳號", "銀行帳號"),
    "currency": ("currency", "幣別"),
}

# A minus sign only counts when it starts a number, not when it is the
# hyphen inside a part code such as HT-SHC-M8X030-12.9-ZNB. Without the
# lookbehind, that part code reads as the amount minus twelve point nine.
_AMOUNT = re.compile(r"(?<![A-Za-z0-9.\-])-?\d[\d,]*(?:\.\d{1,2})?(?![A-Za-z0-9.\-])")
_DATE_PATTERNS = [
    re.compile(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})"),
    re.compile(r"(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})"),
    re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"),
]
_CURRENCY = re.compile(r"\b(TWD|NTD|NT\$|USD|US\$|EUR|JPY|CNY|RMB)\b", re.I)
_PAGE_MARK = re.compile(r"page\s+(\d+)\s*(?:of|/)\s*(\d+)", re.I)
_PAGE_SUBTOTAL = re.compile(
    r"(?:page\s+(?:sub)?total|小計)\s*[:：]?\s*([\d,]+(?:\.\d{1,2})?)", re.I
)

#: A line on an invoice usually reads: number, description, quantity, unit
#: price, amount. The amounts are the last two numbers on the line.
_LINE_START = re.compile(r"^\s*(\d{1,3})[\.\)]?\s+(.+)$")


def _clean_amount(text: str) -> Decimal:
    return dec(text.replace(",", "").strip() or "0")


def _find_date(text: str) -> dt.date | None:
    for pattern in _DATE_PATTERNS:
        found = pattern.search(text)
        if not found:
            continue
        groups = found.groups()
        try:
            if len(groups[0]) == 4:
                return dt.date(int(groups[0]), int(groups[1]), int(groups[2]))
            return dt.date(int(groups[2]), int(groups[1]), int(groups[0]))
        except ValueError:
            continue
    return None


#: A field label is followed by a colon or a run of spaces. Prose is not.
_SEPARATOR = re.compile(r"^\s*[:：]\s*|^\s{2,}|^\t+")


def _labelled_value(line: str, labels: tuple[str, ...]) -> str | None:
    """Read "Bank account: 1234" but not "our new bank account from this month".

    A label only counts when it sits at the start of the line and is followed
    by a separator. Without that rule, any sentence mentioning a bank account
    overwrites the bank account, which is exactly the sort of quiet mistake
    that pays a stranger.
    """
    low = line.lower()
    for label in labels:
        position = low.find(label.lower())
        if position < 0:
            continue
        # The label has to begin the line, give or take a bullet or a number.
        before = line[:position].strip(" \t|-*0123456789.)")
        if before:
            continue
        tail = line[position + len(label) :]
        separator = _SEPARATOR.match(tail)
        if not separator:
            continue
        value = tail[separator.end() :].strip()
        if value:
            return value
    return None


def _apply_barcode(reading: Reading, decoded) -> None:
    """A decoded barcode outranks anything read off the page.

    It is machine written and machine checked. Text is neither, however
    confident whatever read it happens to be.
    """
    if decoded is None:
        return
    reading.barcode = decoded.to_dict()
    if not decoded.well_formed:
        reading.notes.append(f"The barcode could not be used: {decoded.problem}")
        return

    reading.header["invoice_number"] = decoded.invoice_number
    if decoded.invoice_date:
        reading.header["invoice_date"] = decoded.invoice_date.isoformat()
        reading.confidence["invoice_date"] = 1.0
    reading.header["net_amount"] = str(decoded.net_amount)
    reading.header["total_amount"] = str(decoded.total_amount)
    reading.header["tax_amount"] = str(money(decoded.total_amount - decoded.net_amount))
    reading.header["buyer_tax_identifier"] = decoded.buyer_tax_identifier
    reading.header["seller_tax_identifier"] = decoded.seller_tax_identifier
    for name in (
        "invoice_number",
        "net_amount",
        "total_amount",
        "tax_amount",
        "buyer_tax_identifier",
        "seller_tax_identifier",
    ):
        reading.confidence[name] = 1.0
    reading.notes.append(
        "The square barcode was decoded, so its figures are used as the truth."
    )


def read_built_in(text: str, barcode_payload: str = "") -> Reading:
    """Read an invoice with no model, no key and no network."""
    started = time.perf_counter()
    reading = Reading(engine="built-in")
    lines = [line.rstrip() for line in (text or "").splitlines()]

    # --- the square barcode comes first, because it is data, not text ----
    _apply_barcode(reading, read_barcode(barcode_payload))

    # --- labelled header fields -------------------------------------------
    for raw in lines:
        if not raw.strip():
            continue
        for name, labels in _LABELS.items():
            if reading.confidence.get(name, 0) >= 1.0:
                continue  # the barcode already settled it
            if name in reading.header and reading.header[name]:
                continue  # the first reading of a field is the one that counts
            value = _labelled_value(raw, labels)
            if value is None:
                continue
            if name in {"net_amount", "tax_amount", "total_amount"}:
                found = _AMOUNT.search(value)
                if found:
                    reading.header[name] = str(_clean_amount(found.group(0)))
                    reading.confidence[name] = 0.95
            elif name in {"invoice_date", "due_date"}:
                when = _find_date(value)
                if when:
                    reading.header[name] = when.isoformat()
                    reading.confidence[name] = 0.95
            elif name == "currency":
                found = _CURRENCY.search(value)
                if found:
                    reading.header[name] = _normalise_currency(found.group(1))
                    reading.confidence[name] = 0.95
            else:
                cleaned = value.split("  ")[0].strip(" .,;|")
                if cleaned:
                    reading.header[name] = cleaned
                    reading.confidence[name] = 0.92

    # --- the supplier is usually the first substantial line ---------------
    if not reading.header.get("vendor_name"):
        for raw in lines[:6]:
            candidate = raw.strip()
            if len(candidate) > 3 and not _AMOUNT.fullmatch(candidate.replace(" ", "")):
                reading.header["vendor_name"] = candidate
                reading.confidence["vendor_name"] = 0.7
                break

    # --- currency, if nothing said so -------------------------------------
    if not reading.header.get("currency"):
        found = _CURRENCY.search(text or "")
        reading.header["currency"] = (
            _normalise_currency(found.group(1)) if found else settings.base_currency
        )
        reading.confidence["currency"] = 0.8 if found else 0.5

    # --- the lines, page by page ------------------------------------------
    page = 1
    for raw in lines:
        page_mark = _PAGE_MARK.search(raw)
        if page_mark:
            page = int(page_mark.group(1))
            continue
        subtotal = _PAGE_SUBTOTAL.search(raw)
        if subtotal:
            reading.page_subtotals[page] = _clean_amount(subtotal.group(1))
            continue

        parsed = _read_line(raw, page, len(reading.lines) + 1)
        if parsed is not None:
            reading.lines.append(parsed)

    # --- fall back to the lines when a total was not printed --------------
    if reading.lines and not reading.header.get("net_amount"):
        reading.header["net_amount"] = str(
            money(sum((line.line_total for line in reading.lines), Decimal("0")))
        )
        reading.confidence["net_amount"] = 0.6
        reading.notes.append("The amount before tax was added up from the lines.")

    reading.duration_ms = int((time.perf_counter() - started) * 1000)
    return reading


def _normalise_currency(token: str) -> str:
    key = token.upper().replace("$", "").strip()
    return {"NT": "TWD", "NTD": "TWD", "US": "USD", "RMB": "CNY"}.get(key, key or "TWD")


#: Words that mean the row is a heading, a subtotal or a footer, not a line.
_NOT_A_LINE = re.compile(
    r"^(item|no\.?|description|qty|quantity|unit|amount|subtotal|sub total|total|tax|vat|"
    r"page|invoice|bill to|ship to|remit|bank|terms|thank|品名|數量|單價|金額|小計|合計|總計)",
    re.I,
)


def _read_line(raw: str, page: int, position: int) -> ReadLine | None:
    text = raw.strip()
    if len(text) < 6 or _NOT_A_LINE.match(text):
        return None

    numbered = _LINE_START.match(text)
    body = numbered.group(2) if numbered else text

    amounts = _AMOUNT.findall(body)
    if len(amounts) < 2:
        return None

    # The last number is the line amount; the one before it is the unit price;
    # the one before that, if the layout has it, is the quantity.
    line_total = _clean_amount(amounts[-1])
    unit_price = _clean_amount(amounts[-2])
    quantity = _clean_amount(amounts[-3]) if len(amounts) >= 3 else Decimal("0")

    if quantity == 0 and unit_price != 0:
        quantity = (
            money(line_total / unit_price) if unit_price else Decimal("0")
        ).quantize(Decimal("1"))

    # Everything before the first of those numbers is the description.
    cut = body
    for amount in amounts[-3:] if len(amounts) >= 3 else amounts[-2:]:
        index = cut.rfind(amount)
        if index > 0:
            cut = cut[:index]
    description = re.sub(r"\s{2,}", " ", cut).strip(" \t|-,;:x×")
    if not description:
        return None

    part = re.match(r"^([A-Z0-9][A-Z0-9\-/\.]{3,})\s+(.*)$", description)
    part_code = part.group(1) if part else ""

    return ReadLine(
        line_number=position,
        description=description,
        part_code=part_code,
        quantity=quantity,
        unit="piece",
        unit_price=unit_price,
        line_total=line_total,
        page=page,
    )


# ---------------------------------------------------------------------------
# The external engine
# ---------------------------------------------------------------------------
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "header": {
            "type": "object",
            "properties": {name: {"type": "string"} for name in HEADER_FIELDS},
            "required": list(HEADER_FIELDS),
            "additionalProperties": False,
        },
        "confidence": {
            "type": "object",
            "properties": {name: {"type": "number"} for name in HEADER_FIELDS},
            "required": list(HEADER_FIELDS),
            "additionalProperties": False,
        },
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line_number": {"type": "integer"},
                    "description": {"type": "string"},
                    "part_code": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit": {"type": "string"},
                    "unit_price": {"type": "number"},
                    "line_total": {"type": "number"},
                    "page": {"type": "integer"},
                },
                "required": [
                    "line_number", "description", "part_code", "quantity",
                    "unit", "unit_price", "line_total", "page",
                ],
                "additionalProperties": False,
            },
        },
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["header", "confidence", "lines", "notes"],
    "additionalProperties": False,
}

INSTRUCTIONS = """You read supplier invoices and report what is on them.

Rules you must follow:
- Report only what is printed. If a field is not on the document, return an
  empty string for it and a confidence of 0. Never infer, never calculate a
  missing figure, never carry a value over from another field.
- Confidence is how clearly you can read the field, nothing else. A figure you
  had to guess at is below 0.5.
- Copy amounts exactly as printed, without currency symbols or thousands
  separators. Copy identifiers exactly, including letters and leading zeros.
- Return every line item on every page, in order, with the page it came from.
- You are not deciding whether the invoice is correct, whether it matches an
  order, or whether it should be paid. Those are settled elsewhere.
"""


class EngineUnavailable(RuntimeError):
    pass


def read_external(text: str, barcode_payload: str = "") -> Reading:  # pragma: no cover
    """The same reading through a hosted model.

    Deliberately a plain chat-completions request over HTTP. Every hosted
    model worth using speaks that shape, so the product is not married to one
    supplier and there is no package to keep up to date.

    The answer is held to `SCHEMA`. Anything that does not fit is a failure,
    not something to patch up: a reading step that quietly repairs a bad
    answer is a reading step nobody can audit.
    """
    if not settings.model_api_key.strip() or not settings.model_base_url.strip():
        raise EngineUnavailable("No model endpoint is set, so the built-in engine is used.")

    import httpx

    started = time.perf_counter()
    body = {
        "model": settings.model_name,
        "max_tokens": settings.model_max_tokens,
        "temperature": 0,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "invoice_reading", "strict": True, "schema": SCHEMA},
        },
        "messages": [
            {"role": "system", "content": INSTRUCTIONS},
            {"role": "user", "content": text},
        ],
    }
    try:
        response = httpx.post(
            settings.model_base_url.rstrip("/") + "/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.model_api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=settings.model_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        answer = json.loads(payload["choices"][0]["message"]["content"])
    except Exception as error:
        raise EngineUnavailable(f"{type(error).__name__}: {error}") from error

    reading = _reading_from_answer(answer)
    reading.engine = "external"
    reading.duration_ms = int((time.perf_counter() - started) * 1000)

    usage = payload.get("usage") or {}
    reading.notes.append(
        f"Read by {settings.model_name}, "
        f"{usage.get('prompt_tokens', 0)} in and {usage.get('completion_tokens', 0)} out."
    )

    # The barcode is machine-read, so it outranks anything a model says.
    _apply_barcode(reading, read_barcode(barcode_payload))
    return reading


def _reading_from_answer(answer: dict[str, Any]) -> Reading:
    """Hold the model's answer to the schema, and convert it exactly once."""
    if not isinstance(answer, dict):
        raise EngineUnavailable("The answer was not an object.")
    header_in = answer.get("header")
    confidence_in = answer.get("confidence")
    lines_in = answer.get("lines")
    if not isinstance(header_in, dict) or not isinstance(confidence_in, dict):
        raise EngineUnavailable("The answer had no header or no confidence.")
    if not isinstance(lines_in, list):
        raise EngineUnavailable("The answer had no lines.")

    reading = Reading()
    for name in HEADER_FIELDS:
        value = header_in.get(name, "")
        reading.header[name] = "" if value is None else str(value).strip()
        try:
            reading.confidence[name] = max(0.0, min(1.0, float(confidence_in.get(name, 0))))
        except (TypeError, ValueError):
            reading.confidence[name] = 0.0

    for position, row in enumerate(lines_in, start=1):
        if not isinstance(row, dict):
            raise EngineUnavailable(f"Line {position} was not an object.")
        try:
            reading.lines.append(
                ReadLine(
                    line_number=int(row.get("line_number") or position),
                    description=str(row.get("description") or "").strip(),
                    part_code=str(row.get("part_code") or "").strip(),
                    quantity=dec(row.get("quantity") or 0),
                    unit=str(row.get("unit") or "piece").strip() or "piece",
                    unit_price=dec(row.get("unit_price") or 0),
                    line_total=dec(row.get("line_total") or 0),
                    page=int(row.get("page") or 1),
                )
            )
        except (TypeError, ValueError, ArithmeticError) as error:
            raise EngineUnavailable(f"Line {position} could not be used: {error}") from error

    for note in answer.get("notes") or []:
        reading.notes.append(str(note))
    return reading


# ---------------------------------------------------------------------------
# What the rest of the application calls
# ---------------------------------------------------------------------------
def read_invoice(text: str, barcode_payload: str = "", *, force_engine: str = "") -> Reading:
    """Read an invoice, falling back to the built-in engine on any failure."""
    engine = force_engine or settings.reading_engine
    if engine == "external":
        try:
            return read_external(text, barcode_payload)
        except Exception as exc:  # pragma: no cover - depends on configuration
            reading = read_built_in(text, barcode_payload)
            reading.fell_back = True
            reading.notes.append(
                f"The external engine was not used: {exc}. The built-in engine read it."
            )
            return reading
    return read_built_in(text, barcode_payload)


def engine_status() -> dict[str, Any]:
    active = settings.reading_engine
    return {
        "active_engine": active,
        "explanation": (
            "Invoices are read by the built-in engine. No key, no account, no "
            "network and no cost."
            if active == "built-in"
            else "An external model is reading invoices. Every call is on the "
            "invoice timeline with its cost."
        ),
        "guarantee": (
            "Whichever engine reads the page, what is owed is settled by the "
            "checks, the order and the deliveries. The reading engine cannot "
            "approve, match or post anything."
        ),
    }
