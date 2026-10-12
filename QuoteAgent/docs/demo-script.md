# Showing QuoteAgent

Twelve minutes. The product has a built-in **Walkthrough** screen with ten
steps; this script says which to dwell on, what to say over each, and which
to skip when the room is short.

Three moments carry it: the line it refuses to guess, the duty table coming
into force, and the pricing fingerprint at send time. Everything else is
context.

---

## Before they arrive

```bash
python backend/scripts/walkthrough.py        # loads data, drives all ten steps
uvicorn app.main:app --reload --app-dir backend
cd frontend && npm run dev
```

Open <http://localhost:3000> and sign in as
`admin@hengtai-industrial.example` / `demo1234` — the administrator can run
every step, including the two that normally need someone else.

Leave it on **Walkthrough**.

> Steps 7 and 10 need the pricing owner and the sales manager respectively.
> If somebody asks why the administrator can do everything: that is the
> permission model working, and you can show it by signing in as
> `amy.chen@hengtai-industrial.example` (sales engineer) and watching step 10
> refuse.

---

## 0 · Frame it (30 sec)

> "Nine sales engineers, about sixty requests for quotation a week, averaging
> twenty-five lines. Three and a half hours each: decoding specifications,
> translating competitor part numbers, checking stock in two warehouses,
> applying contract prices, converting currency and trade terms. Two to three
> days to turn around — and because pricing lives in people's heads, two reps
> can quote the same customer different prices for the same part."

Then set the frame you want them judging against:

> "I'm going to show you three things it refuses to do. That's the product."

---

## 1 · Forty lines arrive (1 min)

Run step 1.

33 matched, each with a reason. 4 unclear, 1 self-contradicting, 2 not
catalogue parts.

Open a matched line and show the reason — cross-reference, then attributes
verified one by one against the record.

> "A competitor number is matched from a table, not from similarity. Then
> whatever matched gets checked attribute by attribute against the catalogue
> record. A text similarity hit that doesn't verify becomes a question."

If the room is technical, this lands:

> "ISO 15 fixes bearing dimensions, so a 6204 is twenty by forty-seven by
> fourteen from every maker — only the seal suffix differs. SKF calls it
> 2RS1, FAG 2RSR, NSK DDU. Those are interchangeable and the table knows it.
> That's not a model being clever; it's domain data."

---

## 2 · The line it will not guess (2 min) — first moment

Step 2. Open the self-contradicting line.

> "'A2-70 stainless, zinc plated.' Stainless isn't zinc plated. Something is
> wrong with the request and there's no safe way to pick."

It does not choose. It asks.

Now show the questions email — **one email, all nine questions.**

> "Not nine emails. This is the detail that decides whether a customer
> tolerates the thing. And when they answer six of nine, the follow-up asks
> for the three still open — not all nine again."

---

## 3 · Only the unknown lines wait (1 min)

Step 3. Two lines go to a supplier for a price.

> "Two lines wait. Thirty-three carry on and get priced. A prototype blocks
> the whole quote on its slowest line; that's the difference between a demo
> and a product."

Step 5 brings the supplier's answer back and prices those lines with margin
on top.

---

## 4 · The customer replies in Chinese (1 min)

Step 4.

The case resumes where it stopped. The answer settles the attribute it
answers rather than being filed as a note, and the unanswered question is
asked again — alone.

> "Reply goes back in the language they wrote in."

---

## 5 · Trade terms change (1 min)

Step 6. Freight, insurance, duty and currency recomputed, with a before and
after.

Click any figure.

> "Every number opens. Each step in order, the formula in words, and for every
> input the record it came from — which contract, which duty table version,
> which exchange rate on which date."

Leave the panel open for a beat. This is the one people remember.

---

## 6 · A new duty table comes into force (2 min) — second moment

Step 7. **This is a real activation, not a simulation.**

Every open quote priced on the old table is flagged by name, with the reason
written onto each case timeline. This one is re-priced.

> "US duty on Taiwan goods moved three times in 2026. A reciprocal agreement
> in February, Section 232 metals rebuilt in April to apply to full customs
> value, and the Section 301 final action in July capping the combined rate at
> ten per cent without stacking on goods already carrying metals duty.
>
> So duty here is never computed by a model and never written into the code.
> It's read from the table that was in force on the quote date, and the quote
> records which version priced it."

Then the part that matters commercially:

> "When a new table comes in, every open quote priced on the old one gets
> flagged. That's the control. The rates in here are illustrative — a real
> deployment loads its own table with its own broker's sign-off. What you're
> buying is the dated table, the named owner, and the quote that can tell you
> which version priced it."

If asked what happens to an unknown duty code: **refused, not priced at
zero.** Zero produces a quote that is wrong in the customer's favour and
unrecoverable once accepted.

---

## 7 · The customer wants twelve per cent off (1 min)

Step 8. Lines fall below the margin floor and go to the sales manager with
the full price build-up behind each one.

> "An approval here is approval of a *figure*, not of a document. Re-price the
> quote and any approval whose numbers moved re-opens. Otherwise the usual
> thing happens: a manager approves, the duty table changes, and the quote
> goes out at a margin nobody agreed to."

---

## 8 · Revision B (1 min)

Step 9. Six quantities change, two lines added, thirty-four carried over
untouched with their prices intact.

> "It compares against the customer's *original wording*, not against our
> interpretation of it — otherwise a line we read wrongly the first time stays
> wrong through every revision."

---

## 9 · Approve and send (1 min) — third moment

Step 10.

> "Before this quote can go, the server re-computes every figure and compares
> it against a fingerprint stored when the pricing engine produced them. If
> one number has moved — someone edited a row, a duty table changed
> underneath, a rounding bug crept in — the quote is refused and the
> difference is named."

Pause, then:

> "That's the answer to 'what if the AI gets a price wrong'. It can't write
> one. And if anything else writes one, this catches it at the door."

---

## 10 · Acceptance criteria (2 min)

Open **Acceptance criteria**, press **Run it now**.

| Measure | Bar | Measured |
|---|---|---|
| Line matching | ≥92% first attempt | **99.4%** on 1,500 clear lines |
| Ambiguity handling | ≥95% flagged, ≤3% false | **100%** flagged, **0.6%** false |
| Pricing integrity | every price equals the engine's output | **pass** |
| Revisions | every change detected | **100%** |
| Speed | draft in 15 min at p90 for 40 lines | **0.93 s** |
| Edits by the salesperson | median ≤2 lines | **not measured** |

Point at the last row yourself, before they find it:

> "That one we can't measure. It needs real salespeople editing real quotes in
> a pilot. I'd rather show you a blank than a number I made up."

And pre-empt the first one:

> "Ninety-nine point four is against a generated catalogue — realistic noise,
> but built from the same catalogue it's matched against. A real inbox has
> photographs of faxes and part numbers from a paper catalogue nobody
> digitised. Expect the first month of a pilot to be worse than that. The
> ambiguity numbers are the ones I'd trust to transfer, because those measure
> whether it knows when to stop."

---

## Questions you will be asked

**"What if the model invents a price?"**
It cannot write one. Prices, duties, conversion, rounding and totals are
deterministic Python, and the server re-checks every figure against a
fingerprint before a quote can be sent.

**"What does it need to run?"**
Nothing. No key, no account, no network. The reading step has a deterministic
built-in engine as its default. Plugging in a hosted model changes which
component reads free text; it changes nothing about pricing, and a failed call
falls back to the built-in engine rather than stopping the case.

**"How do we know which engine produced a result?"**
It is on screen, on the case timeline, with tokens and cost when a model was
used.

**"Can it send something nobody approved?"**
No. Every outbound email and every sent quote records who approved it, and the
approval rules are evaluated on the server every time the quote is re-priced.

**"Are those time savings real?"**
Unmeasured, and the README says so. They describe a saving that depends on how
your team works. What is measured here is pricing and matching.
