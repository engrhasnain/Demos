# OpsAgent

**Questions about the business, answered from reviewed queries, scoped to what
the asker is allowed to see, with the working shown.**

One of six products built for the same distributor, and the one that sits on
top of the other five: it answers across all of them.

```bash
# terminal one: the backend
python -m venv .venv
.venv\Scripts\activate             # macOS and Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --reload --port 8005 --app-dir backend

# terminal two: the interface
cd frontend && npm install && npm run dev
```

Open <http://localhost:3005>, press **Build the business**, then pick which
reader to sign in as. The password is `demo1234`.

Headless, including the acceptance criteria:

```bash
python backend/scripts/walkthrough.py --evaluate
```

---

## The problem

Managers and sales staff at Hengtai ask around twenty-five cross-system
questions a day — *which of Acme's orders are late, and why*; *if this
supplier's shutdown runs a week long, which customers are hit*. Each takes
about twenty minutes of digging through the business system, the carrier
portal, email and a spreadsheet.

An earlier chatbot pilot was stopped by the technology team over two questions,
and they were the right two:

1. **Will it show people data they are not allowed to see?**
2. **Will it do something nobody approved?**

Those are the top risks in the OWASP list for language-model applications.
Neither can be answered with a prompt, because a prompt is a request and the
model is free to decline it. Both are answered here below the model, in code
and in the database, and then measured by a red team that assumes the model has
already been lost.

## How it answers them

**The model chooses from a closed list and writes the sentence. It does nothing
else.**

```
question
   ↓
planner          picks capability names from a list of 19. Nothing else is sayable.
   ↓
role check       does this person's role reach this capability at all?
   ↓
row filter       wraps the query so it can only return rows their grants allow
   ↓
SQLite           computes every figure
   ↓
writer           turns the rows into a sentence, and is handed nothing but the rows
```

No figure in any answer is produced by anything that writes prose. When an
external model is configured it does the last step only, and is handed the rows
as data with no route back to the database.

Four properties fall out of that shape, and all four are tested:

| | |
|---|---|
| **A fooled planner reaches nothing extra** | The worst it can emit is a capability name and some parameters. An unknown name is refused; a known one runs under the asker's own role check and row filter, neither of which comes from the plan. |
| **Permissions cannot be forgotten** | The filter is attached by the permission module, not by whoever wrote the query. A capability that reads anybody's data and declares no scope column will not load. |
| **No grant means nothing** | An account with no grants gets `WHERE 1 = 0`, never an unfiltered query. |
| **Nothing is ever written** | Every capability is checked for write keywords when the catalogue loads. Approving a proposal records a decision and stops. |

## What it does on screen

A reading room. You hand in a question on a call slip; what comes back is set
like a page in a scholarly edition, with the answer in the text block and the
apparatus in the margin: which query produced each figure, over how many rows,
under which filter, and at what minute it was read.

| Page | |
|---|---|
| **Desk** | Ask. Every sentence carries a reference mark; the mark opens the query behind it. |
| **Index** | All 19 queries, with their SQL. Published on purpose. |
| **Tray** | Things worth doing, waiting for a named person. Nothing acts on them. |
| **Register** | Who called for what, how many rows came back, which filter was on it, and what was refused. |
| **Assurance** | The five bars, measured, with both red teams attack by attack. |

## Measured

Run `python backend/scripts/walkthrough.py --evaluate`, or press **Run it now**
on the Assurance page.

| Bar | Result |
|---|---|
| Answers are right | **19 of 19** against a labelled set that recomputes each answer independently |
| Under a minute | **0.01s** slowest |
| Every number traceable | **19 of 19** carry the query and the moment it was read |
| Permission breaches | **0 rows** from 128 attacks across 4 limited accounts |
| Instructions obeyed from content | **0** from 14 attacks in six families |

The permission suite is the one worth reading. Half of it does not go through
the planner at all: it runs **every capability directly** against a
salesperson's reach, with another account's identifiers as parameters, which is
exactly what a completely subverted planner would emit. No pattern matching, no
refusal text, no keyword filter — only the role check and the row filter are
doing any work.

The injection suite scores on what came out, not on whether the text was
spotted. One of the attacks is written so the keyword check misses it
entirely; it is expected to go unnoticed, and it reaches nothing anyway. That
is the point: nothing in the design depends on noticing.

## Tests

```bash
cd backend && python -m pytest
```

110 tests. The ones worth reading are in
[`tests/test_catalogue.py`](backend/tests/test_catalogue.py), which tests the
rules rather than the current catalogue — each one is a hole somebody could
open by adding a plausible-looking query, and two of them are holes this
product actually had:

- **An ungrouped total over scoped rows.** `SUM(total) … FROM invoices` with a
  bare `customer_id` beside it. The filter wraps the query, so it runs *after*
  the sum. A manager with partial grants would have been shown the whole
  company's money whenever the arbitrary row's customer landed inside their
  grants. Fixed by grouping; prevented from recurring by a check that refuses
  to load an aggregate that is row-scoped and not grouped on its scope column.
- **A scope column named as the query writes it rather than as it outputs it.**
  `scope_column="c.id"` reads correctly and binds to nothing, because the
  filter selects over the subquery's *output*. It failed closed — which meant
  every limited account was refused its own accounts. Now only `customer_id`
  and `supplier_id` are allowed, and the alias has to be in the select list.

## The data

A generated catalogue of about a thousand parts across four families, built the
way a real one grows — every size, class and finish of each line. Orders are
valued from their own lines, invoices are raised against delivered orders, and
weekly demand is the quantity that actually went out, so *weeks of cover* is a
measurement rather than an assertion. It annualises to **US$44.7M** against the
stated ~US$45M, with receivables at **48 days** against roughly 50-day weighted
terms. [`tests/test_seed.py`](backend/tests/test_seed.py) does those sums.

The demonstration data also contains one planted email, `E-9001`, from a
supplier, with instructions in it. Attach it to any question on the Desk.

## Deploying

Both halves to Vercel, as two projects: the Next.js interface, and the FastAPI
backend as Python serverless functions. A hosted PostgreSQL database is
required, because serverless functions have no disk that survives a request —
set `DATABASE_URL`. Set `JWT_SECRET` too; the application refuses to start
outside a demonstration while it is still the published default.

## Further reading

- [`docs/how-it-decides.md`](docs/how-it-decides.md) — the threat model, the
  containment argument, and what this product does not claim.
- [`docs/demo-script.md`](docs/demo-script.md) — twelve minutes, in order.
