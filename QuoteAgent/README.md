# QuoteAgent

**Takes a messy, multi-line request for quotation from the inbox to an approved
quote the same day. It asks instead of guessing, and it never invents a price.**

One of six products built for the same distributor. This is the one that
shows an agent carrying a multi-step business task across days: asking people
when it needs to, handing off at the right moments, and standing up to a line
by line check afterwards.

---

## Run it

Two terminals. Nothing else to install, no account, no key.

**Backend**

```bash
cd QuoteAgent
python -m venv .venv
.venv\Scripts\activate            # macOS and Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --reload --app-dir backend
```

**Frontend**

```bash
cd QuoteAgent/frontend
npm install
npm run dev
```

Then open **http://localhost:3000**, press **Load the demonstration data** (about
ten seconds), and sign in as `admin@hengtai-industrial.example` with the
password `demo1234`. Every demonstration account is listed on the sign-in
screen, and `?as=<email>` signs in directly, which is handy for a walkthrough
link.

The API documents itself at **http://localhost:8000/docs**.

### Or run the whole thing from the command line

```bash
python backend/scripts/walkthrough.py --evaluate
```

That loads the data, drives all ten demonstration steps through the real HTTP
routes, prints what a person would see at each one, checks that every price on
the finished quote still equals the pricing engine's own output, and runs the
acceptance criteria. It exits non-zero if anything fails, so it works as a
smoke test in a pipeline as well as a rehearsal aid.

---

## The problem it solves

Hengtai Industrial Supply's nine sales engineers handle about 60 requests for
quotation a week, averaging 25 lines and sometimes over 100. Each takes about
3.5 hours: decoding specifications, translating competitor and DIN or ISO part
numbers, checking stock in two warehouses, applying contract prices, and
converting currency and trade terms. Turnaround is two to three days, and
because pricing lives in reps' heads and spreadsheets, two reps can quote the
same customer different prices for the same part.

| | Today | With QuoteAgent |
|---|---|---|
| Effort per request | ~3.5 staff-hours | ~45 minutes of review |
| Turnaround | 2–3 days | same day |
| Capacity released | — | ~165 staff-hours a week, roughly four sales engineers |

**Those three rows are illustrative and this product does not measure them.**
They describe a saving that depends on how a particular team works, and no
amount of software testing establishes it. What this repository *does* measure
is on the **Acceptance criteria** screen: pricing accuracy, turnaround on a
labelled set, and how often it asks rather than guesses — reported as measured,
including anything that falls short.

---

## The four rules it is built on

1. **The reasoning engine never writes a number.** Prices, duties, currency
   conversion, pack rounding and totals come from deterministic Python. The
   server stores a fingerprint of every figure the engine produced and
   re-computes it before a quote can be approved or sent. If a single figure
   has moved, the quote is refused and the difference is named.
2. **Every figure can be opened.** Click any price, duty or total and a panel
   shows each step in order, the formula in words, and for every input the
   record it came from: which contract, which duty table version, which
   exchange rate on which date.
3. **It asks instead of guessing.** A line that does not say enough, or that
   contradicts itself, becomes a question. All the open questions go out in
   **one** consolidated email, never one per line, and a customer who answers
   six of nine gets one follow-up asking only for the three still open.
4. **Nothing leaves without a name on it.** Every outbound email and every sent
   quote records who approved it, and the approval rules are evaluated on the
   server every time the quote is re-priced.

### It runs with no key and no account

The step that reads free text has two interchangeable engines behind one strict
schema. The **built-in** engine is deterministic Python: no key, no account, no
network, no cost, and it is the default. An **external model** can be plugged in
instead through one environment variable, in which case every call is listed on
the case timeline with its tokens and its cost, and a failed call falls back to
the built-in engine rather than stopping the case.

Which engine produced a result is always on screen. Neither of them can write a
price.

---

## The hard cases, and where each one is handled

These are the situations that break a happy-path prototype. Every one is built
into the product and into its test set.

| Hard case | What happens | Where |
|---|---|---|
| Competitor and standard part numbers | Cross-reference table, then attribute matching, then text similarity. ISO 15:2017 fixes bearing dimensions, so 6204 is 20 × 47 × 14 mm from every maker and only the seal suffix differs: SKF `2RS1`, FAG `2RSR`, NSK `DDU`, NTN `LLU`, Timken `2RS`. | [`services/matching.py`](backend/app/services/matching.py), [`domain/partnumbers.py`](backend/app/domain/partnumbers.py) |
| Missing or conflicting specifications | The line is flagged, never guessed. "M10 bolt, class 8.8, zinc" is missing a length *and* a head type; "A2-70 stainless, zinc plated" cannot be both. | [`domain/partnumbers.py`](backend/app/domain/partnumbers.py) |
| Nuts and washers graded as bolts | Nuts are class 6, 8, 10 or 12 under ISO 898-2 and washers by hardness under ISO 7089. A "class 8.8 nut" is queried, not quietly matched. | [`domain/partnumbers.py`](backend/app/domain/partnumbers.py) |
| Revisions | Version 2 is compared line by line against the customer's **original** wording. Only changed lines are re-matched and re-priced; the rest are carried over with their prices intact, and the new version carries a change log. | [`services/revisions.py`](backend/app/services/revisions.py) |
| Units, pack sizes, minimum order quantities | Convert to pieces, raise to the supplier minimum if the part is not stocked, then round up to a whole box — in that order, so the customer is never billed for a part box. The rounding is printed on the quote. | [`domain/units.py`](backend/app/domain/units.py) |
| Contract versus list price | Live contract, then the volume break for the customer's price tier, then list. An expired contract falls back and the line is flagged. | [`services/pricing.py`](backend/app/services/pricing.py) |
| Stock split across sites | Options with dates: ship from stock, split the shipment, or wait and ship complete. | [`services/pricing.py`](backend/app/services/pricing.py) |
| Non-stock items | A sub-request goes to the supplier and **only those lines** wait. The other thirty-eight carry on and get priced. | [`services/supplier.py`](backend/app/services/supplier.py) |
| Currency, trade terms, duty | All eleven Incoterms 2020 rules as data. The exchange rate is locked on the quote date. Duty comes from a dated, versioned table that a named person owns and a customs broker signs off. | [`domain/incoterms.py`](backend/app/domain/incoterms.py), [`services/rates.py`](backend/app/services/rates.py) |
| Mixed-language threads | Chinese and English are read, and the reply goes back in the language the customer wrote in. An answer in Chinese settles the attribute it answers, rather than being filed as text. | [`services/clarify.py`](backend/app/services/clarify.py) |
| Margin and authority | Lines below the customer's margin floor go to the sales manager with the price build-up behind each one; quotes over the threshold go to a director. Re-pricing re-opens an approval whose numbers have moved. | [`services/approvals.py`](backend/app/services/approvals.py) |

---

## Duty, and why it is a table and not a model

United States duty on Taiwan goods changed repeatedly in 2026: a reciprocal
trade agreement set an all-in rate in February, the Section 232 metals duty was
rebuilt in April to apply to the full customs value rather than the metal
content, and the Section 301 final action of 24 July capped the combined rate
for Taiwan at 10 per cent, without stacking on goods that already carry the
metals duty.

So duty here is never computed by a model and never written into the code. It
is read from the one table that was active on the quote date. Each quote records
which version priced it. Bringing a newer table into force flags **every open
quote priced on an older one**, by name, with the reason written onto each case
timeline — that is step seven of the walkthrough, and it is a real activation,
not a simulation.

The rates in the demonstration data are illustrative. The control the product
enforces is the real deliverable: a dated table, a named owner, a broker
sign-off, and a quote that says which version priced it.

---

## The ten step walkthrough

Open **Walkthrough** in the interface, or run
`python backend/scripts/walkthrough.py`. Each step performs the real action.

| # | Step | What it proves |
|---|------|----------------|
| 1 | A forty line request arrives | 33 lines matched with a reason each; 4 unclear, 1 self-contradicting, 2 not catalogue parts |
| 2 | The line that contradicts itself | The agent does not choose. One consolidated email of questions, waiting for approval |
| 3 | A price request to a supplier | Two lines wait; thirty-three carry on and get priced |
| 4 | The customer replies in Traditional Chinese | The case resumes where it stopped; the unanswered question is asked again, alone |
| 5 | The supplier answers | Those lines are priced with Hengtai's margin on top |
| 6 | The trade terms change | Freight, insurance, duty and currency recomputed, with a before and after |
| 7 | A new duty table comes into force | Every open quote priced on the old table is flagged; this one is re-priced |
| 8 | The customer asks for twelve per cent off | Lines fall below the margin floor and go to the sales manager with the build-up |
| 9 | Revision B of the bill of materials | Six quantities change, two lines are added; thirty-four are carried over untouched |
| 10 | Approve and send | The quote is produced, with the pricing fingerprint verified first |

Step seven needs the pricing owner's role and step ten needs the sales
manager's. That is the permission model working, not a fault; sign in as the
administrator to run the whole script in one go.

---

## Acceptance criteria

Five bars, run as code against a labelled test set built from the catalogue —
not read off a report somebody wrote afterwards. Open **Acceptance criteria**
and press **Run it now**, or:

```bash
python backend/scripts/walkthrough.py --evaluate
```

| Measure | Pass bar | Last measured here |
|---|---|---|
| Line matching | 92% or more correct at the first attempt | **99.4%** on 1,500 clear lines |
| Ambiguity handling | 95%+ of unclear lines flagged, ≤3% of clear lines wrongly flagged | **100%** flagged, **0.6%** wrongly flagged |
| Pricing integrity | every price equals the engine's own output | **pass**, by re-computing the fingerprint |
| Revisions | every change between two versions detected | **100%** |
| Speed | a draft within 15 minutes at the 90th percentile for 40 lines | **0.93 s** of agent working time |
| Edits by the salesperson | median of 2 lines or fewer changed | **not measured** — needs a pilot |

The last row is reported as not measured rather than estimated. The product
records the draft and the sent version of every quote, so it becomes measurable
in the first week of a pilot.

Figures move slightly between runs because the test set is drawn from the
generated catalogue. Run it yourself; the screen shows every line it got wrong,
in full.

---

## How it is put together

```
backend/
  app/
    domain/          industry rules with no database and no web layer
      partnumbers.py   reading DIN/ISO fasteners, ISO 15 bearings, ISO 15552 cylinders
      units.py         pieces, boxes, pack rounding, supplier minimums
      incoterms.py     all eleven Incoterms 2020 rules as data
      taxid.py         Taiwan unified business number, post-2023 divide-by-five rule
    services/
      intake.py        email threads and attachments; spreadsheets read by code
      reasoning.py     the two engines, the strict schema, the cost accounting
      matching.py      four routes to a part, then verification attribute by attribute
      pricing.py       the only place that decides what something costs
      rates.py         currency, freight and the dated duty tables
      clarify.py       one consolidated email; answers read into attribute values
      supplier.py      sub-requests that do not block the other lines
      revisions.py     version 2 compared with version 1
      approvals.py     margin floor, quote value, non-catalogue parts, unsigned duty
      agent.py         the steps in order, with everything written down
      documents.py     the quote document and the line export
      casestate.py     the lifecycle, and the moves it refuses
    routers/         the HTTP surface
    seed/            the generator that builds Hengtai, and the sample requests
    evaluation/      the acceptance criteria, run as code
  tests/             111 tests
  scripts/
    walkthrough.py      the whole demonstration from the command line
    diagnose_matching.py  line by line, what the matcher did and why
frontend/
  src/app/           overview, requests, walkthrough, catalogue, duty, acceptance
  src/components/    the trace panel, the ledger, the shell
```

### Technical choices

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2 | Exact decimals, strict schemas, and one language for the engine and the rules |
| Database | SQLite by default, PostgreSQL via `DATABASE_URL` | A reviewer needs nothing installed; anything deployed needs PostgreSQL |
| Money | `Decimal` everywhere, stored as exact text | Floats lose cents on a hundred-line bill of materials |
| Sign-in | Standard library only (pbkdf2 and hmac) | A demonstration that will not start because a password library failed to compile is a demonstration that does not get shown |
| Search | An in-process index over 18,000 parts | Explainable on screen, and one fewer service that can be down |
| Frontend | Next.js 15, TypeScript, Tailwind CSS 4 | Deploys to Vercel as an ordinary project, alongside the backend |

### Settings

Everything has a working default. Copy `.env.example` to `.env` to change any of
it.

| Variable | Default | What it does |
|---|---|---|
| `DATABASE_URL` | a SQLite file under `backend/var` | `postgresql+psycopg://…` for PostgreSQL |
| `MODEL_API_KEY` | empty | Optional. Routes the reasoning step to an external model instead of the built-in one. |
| `MODEL_NAME` | empty | Which model, when a key is set |
| `JWT_SECRET` | a demonstration value | Optional for a demonstration; set it for anything else |
| `DIRECTOR_APPROVAL_THRESHOLD_TWD` | 1,500,000 | Above this a director approves |
| `DEFAULT_MARGIN_FLOOR_PERCENT` | 18 | Below this a sales manager approves |
| `AUTO_LOAD_DEMO_DATA` | on where storage is temporary (Vercel + SQLite), off elsewhere | `false` turns the start-up load off, `true` turns it on anywhere |
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` in development; empty (same origin) in production builds | Where the interface looks for the backend |

---

## Deploying

**One Vercel project, zero setup.** Import the repository, set the Root
Directory to `QuoteAgent`, press Deploy. `vercel.json` runs the interface and
the API as two services behind one URL (`/api/*` to the backend, everything
else to the interface), so there is no CORS and no address to configure.

No database is needed: on Vercel the backend uses a SQLite file in `/tmp` and
fills it with the demonstration data (1,000 parts, 80 customers, two dozen
worked requests) on the first request after a start, so the site opens with
data and `admin@hengtai-industrial.example` / `demo1234` signs in straight
away. The data resets when the server restarts, and a thin bar says so.
Setting `DATABASE_URL` to PostgreSQL (plus `JWT_SECRET`) is the optional
upgrade that keeps it.

Step by step, including what to do when it does not work:
**[docs/deploying-to-vercel.md](docs/deploying-to-vercel.md)**.

---

## What is real and what is generated

**Real:** the matching, the pricing engine, the duty stacking rules, the
approval rules, the state machine, the document generation, the permission
model, the test suite and the measured acceptance criteria.

**Generated:** Hengtai Industrial Supply and everything in it — 18,000 parts,
1,200 customers, 140 suppliers, the contracts, the stock, the duty tables and
the sample requests. All of it from a fixed seed, so two people see the same
data, including the same duplicate supplier records, parts with no stock, and
contracts that have run out.

**Not in this MVP:** reading CAD drawings, scanned paper with no text layer,
live integration with a business system or a customer relationship system, live
carrier freight rates, and sending a quote without a person approving it.

---

## Tests

```bash
cd backend
python -m pytest -q          # 111 tests, about 15 seconds
```

They cover the industry rules (part numbers, units, tax identifiers, trade
terms), the pricing engine including duty stacking and the integrity
fingerprint, all four matching routes and the cases where matching must refuse
to answer, the lifecycle, the permission model, and the whole ten step
walkthrough end to end.

`python backend/scripts/diagnose_matching.py` prints what the matcher did with
every line of the sample bill of materials and why — the fastest way to see a
change's effect.

---

## Further reading

- [`docs/how-it-decides.md`](docs/how-it-decides.md) — every decision in the
  order it runs, and what this product does not claim.
- [`docs/demo-script.md`](docs/demo-script.md) — twelve minutes, in order,
  with the awkward questions and how to answer them.
- [`docs/architecture.md`](docs/architecture.md) — the shape of the system,
  for engineers reviewing the build.
- [`docs/evaluation-report.md`](docs/evaluation-report.md) — the measured
  numbers, generated from a real run.
- [`docs/deploying-to-vercel.md`](docs/deploying-to-vercel.md) — putting it
  on a URL.
