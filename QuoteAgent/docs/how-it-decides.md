# How QuoteAgent decides, and what it does not claim

Written for the engineer reviewing the build and the manager deciding whether
to put it in front of customers. For the *shape* of the system — the stages
and what passes between them — see
[`architecture.md`](architecture.md). This note is about the decisions, and
about where the claims stop.

---

## 1. The rule everything else hangs off

> **The reasoning engine never writes a number.**

Prices, duties, currency conversion, pack rounding and totals come from
deterministic Python. The engine that reads free text may decide *what a line
means*; it may not decide what a line costs.

This is not enforced by convention. The server stores a **fingerprint** of
every figure the pricing engine produced, and re-computes it before a quote
can be approved or sent. If a single figure has moved — because somebody
edited a row, or a duty table changed underneath, or a bug crept into a
rounding rule — the quote is refused and the difference is named.

So the honest statement of trust is:

| Component | Trusted with |
|---|---|
| The reading engine | What the customer probably meant |
| Deterministic code | Every figure, without exception |
| The server, at send time | Re-checking that the figures are still the ones the code produced |

Swapping the built-in engine for a hosted model changes the first row and
nothing else.

---

## 2. Matching a line to a part

Three stages, in order, and the order matters:

1. **Cross-reference table** — a known competitor or standard number maps to a
   catalogue part. Exact, from data.
2. **Attribute matching** — the line is decomposed into attributes (thread,
   length, class, finish, seal) and matched attribute by attribute against the
   record.
3. **Text similarity** — last, and only to *propose*.

Whatever stage produced a candidate, the result is then **verified attribute
by attribute against the catalogue record**. A text-similarity hit that does
not verify is a question, not a match.

The domain knowledge is real and it is the reason this works:

- **ISO 15:2017** fixes bearing dimensions, so a 6204 is 20 × 47 × 14 mm from
  every maker and only the seal suffix differs — SKF `2RS1`, FAG `2RSR`, NSK
  `DDU`, NTN `LLU`, Timken `2RS`. Those are interchangeable and the table says
  so.
- **ISO 898-2** grades nuts as class 6, 8, 10 or 12; bolts are 8.8, 10.9,
  12.9. A "class 8.8 nut" is therefore not a nut grade at all, and it is
  queried rather than quietly matched to something plausible.
- **ISO 7089** grades washers by hardness, not by bolt class, for the same
  reason.

### When it asks instead of guessing

A line is flagged when it is **under-specified** ("M10 bolt, class 8.8, zinc"
has no length and no head type) or **self-contradicting** ("A2-70 stainless,
zinc plated" — stainless is not zinc plated).

All open questions go out in **one consolidated email**, never one per line.
A customer who answers six of nine gets a single follow-up asking only for the
three still open. This is a product decision as much as a technical one: nine
emails about one order is how an automation gets switched off.

---

## 3. Pricing, in the order the rules run

**Which price.** Live contract → volume break for the customer's price tier →
list. An expired contract falls back *and the line is flagged*, because a
silently-expired contract is how a customer gets quoted a price nobody agreed.

**How many.** Convert to pieces → raise to the supplier minimum if the part is
not stocked → round up to a whole box. **In that order.** Reversing the last
two bills the customer for a part box. The rounding is printed on the quote,
so the customer sees why they are being sold 250 when they asked for 220.

**Exact decimals throughout.** `Decimal`, stored as text. A float loses cents
on a hundred-line bill of materials, and a quote that is four cents out is a
quote somebody has to explain.

**The exchange rate is locked on the quote date** and recorded. A quote
re-opened next week prices at the rate it was quoted at, not today's.

---

## 4. Duty: a table, never a model

United States duty on Taiwan goods moved repeatedly through 2026 — a
reciprocal trade agreement setting an all-in rate in February, Section 232
metals duty rebuilt in April to apply to full customs value rather than metal
content, and the Section 301 final action of 24 July capping the combined rate
for Taiwan at 10% without stacking on goods already carrying the metals duty.

Duty is therefore **never computed by a model and never written into the
code**. It is read from the one table that was active on the quote date, and
each quote records which version priced it.

Bringing a newer table into force flags **every open quote priced on an older
one**, by name, with the reason written onto each case timeline.

A missing duty row is **refused, not priced at zero**. Pricing an unknown duty
at nothing produces a quote that is wrong in the customer's favour and
unrecoverable once accepted.

> The rates in the demonstration data are illustrative. The *control* is the
> product: a dated table, a named owner, a broker sign-off, and a quote that
> says which version priced it.

---

## 5. Authority

Lines below the customer's margin floor go to the sales manager, with the
price build-up behind each one. Quotes over the threshold go to a director.

The rule that makes this worth having: **re-pricing re-opens an approval whose
numbers have moved.** An approval is approval of a figure, not of a document.
Without that, the common failure is a manager approving a quote, the duty
table changing, and the approved quote going out at a margin nobody agreed to.

Every outbound email and every sent quote records who approved it.

---

## 6. Revisions

Version 2 is compared line by line against the customer's **original
wording**, not against our interpretation of it. Only changed lines are
re-matched and re-priced; the rest carry over with their prices intact, and
the new version carries a change log.

Comparing against our own interpretation would mean a line we read wrongly the
first time silently stays wrong through every revision.

---

## 7. What this does not claim

- **It does not claim the business case.** The README's three rows — 3.5
  staff-hours down to 45 minutes, 2–3 days down to same day, ~165 hours a week
  released — are **illustrative and unmeasured**. They depend on how a
  particular team works and no amount of software testing establishes them.
  What is measured is on the Acceptance criteria screen, and it is about
  pricing and matching, not about saving.
- **One acceptance bar is openly unmet.** "Median of 2 lines or fewer edited
  by the salesperson" is reported as **not measured — needs a pilot**, because
  it cannot be measured without real salespeople editing real quotes.
  Inventing a number for it would be the easiest dishonest thing in this
  repository.
- **99.4% matching is against a generated catalogue.** The lines are built
  from the same catalogue they are matched against, with realistic noise. A
  real inbox contains handwriting, photographs of faxes and part numbers from
  a 1998 paper catalogue nobody has digitised. Expect the first month of a
  pilot to be worse than this figure, and treat the *ambiguity* numbers as the
  more transferable ones.
- **The duty rates are not advice.** They are demonstration data shaped like
  the real 2026 changes. A deployment loads its own table, signed off by its
  own broker. Nobody should price a real shipment from this repository.
- **Supplier price requests are simulated.** The sub-request flow is real —
  only the waiting lines wait, the other thirty-eight get priced — but there
  is no live supplier on the other end.
- **It cannot read what is not there.** A line with no length and no head type
  becomes a question. That is correct behaviour, and it means the product's
  throughput depends on how well customers write their requests. A customer
  who sends consistently vague lines will see a lot of questions, and that is
  the system working.
