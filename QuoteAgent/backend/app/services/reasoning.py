"""The reasoning engine, and the rule that it never writes a number.

Two engines produce exactly the same shape of answer:

* **built-in** - deterministic Python. No key, no account, no network, no cost.
  This is the default, so the product can be demonstrated anywhere.
* **external** - the same step through a hosted language model, used only when
  a key is configured. Structured output keeps the answer inside the schema,
  and every call records its tokens and its cost on the case timeline.

What the engine is allowed to do is deliberately narrow: read messy text into
line items, judge whether a line is ambiguous, and draft wording for a question
or an email. Prices, duties, currency conversion, pack rounding and totals are
worked out by the pricing engine and are re-checked by the server before
anything can be saved. The engine proposes; code verifies.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from ..config import settings
from ..domain.partnumbers import normalise_text
from ..money import dec

# ---------------------------------------------------------------------------
# What a request cost to read, so the timeline can show it.
#
# The rate is a setting rather than a built-in table: only the operator knows
# what they pay, and a price list in the source is wrong within the month.
# ---------------------------------------------------------------------------
def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    million = Decimal("1000000")
    price_in = dec(settings.model_input_cost_per_million)
    price_out = dec(settings.model_output_cost_per_million)
    return (
        dec(input_tokens) / million * price_in + dec(output_tokens) / million * price_out
    ).quantize(Decimal("0.000001"))


@dataclass(slots=True)
class ReasoningResult:
    """What came back, and what it cost to get it."""

    value: Any
    engine: str
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    duration_ms: int = 0
    notes: list[str] = field(default_factory=list)
    fell_back: bool = False

    def as_event_detail(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": str(self.cost_usd),
            "duration_ms": self.duration_ms,
            "notes": self.notes,
            "fell_back_to_built_in": self.fell_back,
        }


# ---------------------------------------------------------------------------
# The schema both engines must fill
# ---------------------------------------------------------------------------
LINE_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line_number": {"type": "integer"},
                    "description": {
                        "type": "string",
                        "description": "The part description exactly as the customer wrote it.",
                    },
                    "customer_reference": {
                        "type": "string",
                        "description": "The customer's own line or drawing reference, or an empty string.",
                    },
                    "quantity": {
                        "type": "number",
                        "description": "The number asked for. Never a price and never a total.",
                    },
                    "unit": {
                        "type": "string",
                        "description": "pieces, boxes, sets or thousands, as written.",
                    },
                    "requested_date": {
                        "type": "string",
                        "description": "ISO date the customer needs it by, or an empty string.",
                    },
                },
                "required": [
                    "line_number",
                    "description",
                    "customer_reference",
                    "quantity",
                    "unit",
                    "requested_date",
                ],
                "additionalProperties": False,
            },
        },
        "language": {
            "type": "string",
            "description": "Two letter code of the language the customer wrote in.",
        },
        "incoterm": {
            "type": "string",
            "description": "An Incoterms 2020 rule if the customer named one, otherwise empty.",
        },
        "named_place": {"type": "string"},
        "currency": {"type": "string"},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["lines", "language", "incoterm", "named_place", "currency", "notes"],
    "additionalProperties": False,
}

READER_INSTRUCTIONS = """You read business-to-business requests for quotation at an \
industrial parts distributor and turn them into line items.

Rules you must follow:
- Copy the part description exactly as the customer wrote it. Do not translate it, \
do not tidy it, do not expand abbreviations and do not guess a part number.
- Quantity is the number of items asked for. Never read a price, a drawing number, \
a length or a line total as a quantity.
- If a line has no quantity, use 0 and say so in notes.
- Never invent a line that is not in the text. Never merge two different parts.
- Never state a price. Pricing is not your job and any price you write will be discarded.
- Return the language the customer wrote in as a two letter code, for example en or zh.
"""


# ---------------------------------------------------------------------------
# Built-in engine
# ---------------------------------------------------------------------------
_LINE_START = re.compile(r"^\s*(?:(\d{1,3})[\.\)]\s+|[-*•]\s+)")
_QUANTITY_PATTERNS = [
    re.compile(r"(?:qty|quantity|q'?ty|數量|數量:)\s*[:=]?\s*([\d,]+(?:\.\d+)?)\s*([a-z一-鿿]*)", re.I),
    re.compile(r"\b([\d,]+(?:\.\d+)?)\s*(pcs?|pieces?|ea|each|sets?|boxes?|box|k|支|個|件|組|盒)\b", re.I),
    re.compile(r"[x×]\s*([\d,]{2,})\s*$"),
]
_DATE_RE = re.compile(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b")
_INCOTERM_RE = re.compile(
    r"\b(EXW|FCA|FAS|FOB|CFR|CIF|CPT|CIP|DAP|DPU|DDP)\b(?:\s+([A-Za-z 一-鿿]{2,30}))?"
)
_CURRENCY_RE = re.compile(r"\b(USD|TWD|NTD|NT\$|US\$|EUR|JPY|RMB|CNY)\b", re.I)
_CJK_RE = re.compile(r"[一-鿿]")

#: Lines that are headers, totals or courtesy text, not parts.
_NOISE = re.compile(
    r"^(dear|hi|hello|regards|best|thanks|thank you|please|kind regards|attached|"
    r"total|subtotal|sub total|grand total|page \d|item\s+description|no\.?\s+part|"
    r"您好|謝謝|敬上|附件|合計|總計)\b",
    re.I,
)


def _clean_number(text: str) -> Decimal:
    return dec(text.replace(",", "").strip() or "0")


def _looks_like_part(text: str) -> bool:
    low = normalise_text(text)
    if len(low) < 4 or _NOISE.match(low):
        return False
    signals = (
        "din", "iso", "m3", "m4", "m5", "m6", "m8", "m10", "m12", "m14", "m16",
        "m18", "m20", "m22", "m24", "bolt", "screw", "nut", "washer", "bearing",
        "cylinder", "valve", "fitting", "pneumatic", "stud", "socket", "hex",
        "螺絲", "螺栓", "螺帽", "墊圈", "軸承", "氣缸",
    )
    if any(s in low for s in signals):
        return True
    return bool(re.search(r"\b6[0-3]\d{2}\b", low)) or bool(re.search(r"\b\d{6,}\b", low))


def read_lines_built_in(text: str) -> dict[str, Any]:
    """Read a request into line items with no model and no network."""
    started = time.perf_counter()
    lines: list[dict[str, Any]] = []
    notes: list[str] = []

    for raw in (text or "").splitlines():
        candidate = raw.strip()
        if not candidate or not _looks_like_part(candidate):
            continue

        number_match = _LINE_START.match(candidate)
        body = _LINE_START.sub("", candidate)

        quantity = Decimal("0")
        unit = "piece"
        for pattern in _QUANTITY_PATTERNS:
            found = pattern.search(body)
            if found:
                quantity = _clean_number(found.group(1))
                if found.lastindex and found.lastindex >= 2 and found.group(2):
                    unit = found.group(2)
                body = body[: found.start()] + body[found.end():]
                break
        if quantity == 0:
            notes.append(f"No quantity found on the line: {candidate[:60]}")

        date_match = _DATE_RE.search(body)
        requested_date = ""
        if date_match:
            year, month, day = date_match.groups()
            requested_date = f"{year}-{int(month):02d}-{int(day):02d}"
            body = body.replace(date_match.group(0), " ")

        reference = ""
        reference_match = re.search(r"\b(?:ref|our ref|dwg|drawing)\.?\s*[:#]?\s*([A-Z0-9\-/]{3,})", body, re.I)
        if reference_match:
            reference = reference_match.group(1)

        description = re.sub(r"\s{2,}", " ", body).strip(" \t|-,;:")
        if not description:
            continue

        lines.append(
            {
                "line_number": int(number_match.group(1)) if number_match and number_match.group(1) else len(lines) + 1,
                "description": description,
                "customer_reference": reference,
                "quantity": float(quantity),
                "unit": unit,
                "requested_date": requested_date,
            }
        )

    # Renumber so the quote always reads 1, 2, 3 even if the customer did not.
    for index, line in enumerate(lines, start=1):
        line["line_number"] = index

    incoterm, named_place = "", ""
    incoterm_match = _INCOTERM_RE.search(text or "")
    if incoterm_match:
        incoterm = incoterm_match.group(1).upper()
        named_place = (incoterm_match.group(2) or "").strip(" .,;")

    currency = ""
    currency_match = _CURRENCY_RE.search(text or "")
    if currency_match:
        raw_currency = currency_match.group(1).upper().replace("$", "").replace("NT", "TWD")
        currency = {"USD": "USD", "US": "USD", "TWD": "TWD", "NTD": "TWD",
                    "EUR": "EUR", "JPY": "JPY", "RMB": "CNY", "CNY": "CNY"}.get(raw_currency, "")

    language = "zh" if len(_CJK_RE.findall(text or "")) >= 4 else "en"

    return {
        "lines": lines,
        "language": language,
        "incoterm": incoterm,
        "named_place": named_place,
        "currency": currency,
        "notes": notes,
        "_duration_ms": int((time.perf_counter() - started) * 1000),
    }


# ---------------------------------------------------------------------------
# The external engine
# ---------------------------------------------------------------------------
class ModelUnavailable(RuntimeError):
    pass


def read_lines_with_model(text: str, *, context: str = "") -> ReasoningResult:
    """The same reading step through a hosted model, held to the same schema.

    Deliberately a plain chat-completions request over HTTP. Every hosted
    model worth using speaks that shape, so the product is not married to one
    supplier and there is no client package to keep up to date.
    """
    if not settings.model_api_key.strip() or not settings.model_base_url.strip():
        raise ModelUnavailable("No model endpoint is set, so the built-in engine is used.")

    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise ModelUnavailable(
            "The HTTP client is not installed, so the built-in engine is used."
        ) from exc

    started = time.perf_counter()
    model = settings.model_name or "default"
    body = {
        "model": model,
        "max_tokens": settings.model_max_tokens,
        "temperature": 0,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "request_lines",
                "strict": True,
                "schema": LINE_ITEM_SCHEMA,
            },
        },
        "messages": [
            {
                "role": "system",
                "content": READER_INSTRUCTIONS + (f"\n\n{context}" if context else ""),
            },
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
        value = json.loads(payload["choices"][0]["message"]["content"])
    except Exception as error:
        raise ModelUnavailable(f"{type(error).__name__}: {error}") from error

    usage = payload.get("usage") or {}
    input_tokens = int(usage.get("prompt_tokens", 0) or 0)
    output_tokens = int(usage.get("completion_tokens", 0) or 0)

    return ReasoningResult(
        value=value,
        engine="external",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=estimate_cost(model, input_tokens, output_tokens),
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


# ---------------------------------------------------------------------------
# What the rest of the application calls
# ---------------------------------------------------------------------------
def read_request_lines(text: str, *, context: str = "", force_engine: str = "") -> ReasoningResult:
    """Turn a request for quote into line items.

    Falls back to the built-in engine on any failure, and says so, because a
    demonstration that stops because a network call timed out is worse than a
    demonstration that quietly carries on with deterministic code.
    """
    engine = force_engine or settings.reasoning_engine

    if engine == "external":
        try:
            return read_lines_with_model(text, context=context)
        except ModelUnavailable as exc:
            fallback = read_lines_built_in(text)
            return ReasoningResult(
                value=fallback,
                engine="built-in",
                duration_ms=fallback.pop("_duration_ms", 0),
                notes=[str(exc)],
                fell_back=True,
            )
        except Exception as exc:  # pragma: no cover - network and provider faults
            fallback = read_lines_built_in(text)
            return ReasoningResult(
                value=fallback,
                engine="built-in",
                duration_ms=fallback.pop("_duration_ms", 0),
                notes=[
                    "The external model could not be reached, so the built-in "
                    f"engine read the request instead. Reason: {type(exc).__name__}"
                ],
                fell_back=True,
            )

    result = read_lines_built_in(text)
    return ReasoningResult(
        value=result, engine="built-in", duration_ms=result.pop("_duration_ms", 0)
    )


def engine_status() -> dict[str, Any]:
    """Shown on screen so nobody has to wonder which engine produced a result."""
    active = settings.reasoning_engine
    # `reasoning_engine` answers "external" or "built-in". Comparing it to a
    # supplier's name meant the model was never named on screen.
    return {
        "active_engine": active,
        "model": settings.model_name if active == "external" else "",
        "endpoint_configured": bool(settings.model_base_url.strip()),
        "api_key_present": bool(settings.model_api_key.strip()),
        "budget_usd_per_case": settings.reasoning_budget_usd_per_case,
        "explanation": (
            "An external language model is reading requests. Every call is listed "
            "on the case timeline with its tokens and its cost."
            if active == "external"
            else "Requests are read by the built-in engine. No key, no account, no "
            "network and no cost."
        ),
        "guarantee": (
            "Whichever engine is active, prices, duties, currency conversion and "
            "totals are produced by the pricing engine alone and are re-checked by "
            "the server before a quote can be saved or sent."
        ),
    }
