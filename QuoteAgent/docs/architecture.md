# QuoteAgent: architecture note

Written for: engineers reviewing the build, and the product owner deciding
whether it is the right shape to take into a pilot.

---

## 1. The shape of the thing

```
  email + attachments
         │
         ▼
   ┌───────────┐   spreadsheets read by code, never by a model
   │  intake   │   the same email twice produces one case
   └─────┬─────┘
         ▼
   ┌───────────┐   built-in engine, or an external model when a key is set
   │  reading  │   strict schema; it may not write a price
   └─────┬─────┘
         ▼
   ┌───────────┐   catalogue number → cross-reference → attributes → text
   │ matching  │   then VERIFIED attribute by attribute against the record
   └─────┬─────┘
         │
         ├──► unclear or contradictory ──► one consolidated question email
         ├──► not a catalogue part ──────► one sub-request to a supplier
         ▼
   ┌───────────┐   contract → volume break → list; packs; margin; freight;
   │  pricing  │   duty from a dated table; currency at a locked rate
   └─────┬─────┘   every step writes a trace
         ▼
   ┌───────────┐   margin floor, quote value, non-catalogue, unsigned duty
   │ approvals │   re-evaluated every time the quote is re-priced
   └─────┬─────┘
         ▼
   ┌───────────┐   fingerprint re-computed and compared before anything goes
   │   send    │
   └───────────┘
```

Each box is one module under `backend/app/services/`. The arrows are the only
way between them, and the case lifecycle in `casestate.py` refuses any move
that is not on its map.

## 2. The two rules everything else follows from

### The reasoning engine may not write a number

`services/reasoning.py` has one job: turn free text into line items against a
strict schema. It is given no tool that returns money, and the schema it fills
has no price field. Prices come from `services/pricing.py`, which is ordinary
Python with no model anywhere near it.

That is a claim, so it is made checkable. When a quote version is priced, the
server stores a SHA-256 fingerprint of every figure the engine produced:
quantities, unit prices, line totals, duty, and the shipment totals. Before a
quote can be approved or sent, `verify_pricing_integrity` re-runs the engine
and compares. A single figure out of place refuses the send and names the
difference.

One subtlety worth knowing: the fingerprint canonicalises each number before
hashing, because `Decimal("0.00")` and `Decimal("0")` are equal and the database
does not rewrite a column whose value compares equal. Without that, the check
reported differences where there were none and blocked every quote. The fix is
in `pricing.canonical_amount`, and a test holds it in place.

### Every figure carries its own derivation

`money.Trace` is a list of steps. Each step has a label, the formula written
out, the result, and for every input: the value, the kind of record it came
from, and that record's identifier. The pricing engine appends to a trace as it
goes, and the trace is stored on the line.

The interface renders any figure with a trace as a button. That is the whole of
"every number can be clicked": there is no separate explanation system to drift
out of step with the arithmetic, because the explanation *is* the arithmetic.

## 3. Matching, and when it refuses

Four routes, tried in order:

1. **Hengtai's own catalogue number**, written any way a human writes it.
2. **The cross-reference table** — competitor numbers and published standards.
3. **Attribute matching** — read the specification, filter the catalogue on it.
4. **Text similarity** — a character trigram index over the catalogue.

Whichever answers, the answer is then **verified**: every attribute the customer
actually wrote has to agree with the catalogue record, or the candidate is
rejected. Attributes the agent filled in itself — normal clearance on a bearing
that did not state one — are advisory, and disagreeing with an assumption lowers
confidence instead of rejecting.

Three deliberate refusals:

* **Text similarity never matches on its own.** A part Hengtai does not list
  always looks a bit like one it does. A similarity hit with no verified
  attribute behind it becomes "not a catalogue part", with the nearest listed
  part offered as information.
* **A bare bearing number with no maker does not settle the sealing.** "SKF
  6307" is a complete designation and means the open bearing. A bare "6307" is
  usually somebody who has not written the suffix down, and shipping an open
  bearing to somebody who wanted 2RS is the most expensive mistake in the
  category.
* **A line naming a published standard Hengtai does not stock** (ISO 7379
  shoulder screws, for instance) is handed to a supplier, not forced onto a
  near neighbour.

Conversely, a line that quotes one of our own catalogue numbers is settled by
that number: the catalogue record supplies whatever the written words left out.
Asking a customer for the finish of a part they identified by number would be
absurd.

## 4. Why duty is a table

United States duty on Taiwan goods changed repeatedly through 2026. Any rate
written into code, or produced by a model, would have been wrong within weeks.

`TariffTable` is dated and versioned, owned by a named person, and carries a
customs broker sign-off. `TariffLine` holds one duty component for one
commodity code on one trade lane, with its basis (full customs value or metal
content), what it is not stacked with, and an optional combined cap. The
stacking rules fall out of the data:

* a steel fastener carrying the Section 232 metals duty is **not** also given
  the Section 301 layer, because the 301 row names 232 in `excluded_by`;
* a bearing, which is not a steel derivative, gets the Section 301 rate reduced
  so the combined rate stops at the 10 per cent cap for Taiwan.

A quote records which table version priced it. Bringing a newer table into force
flags every open quote priced on an older one and writes the reason onto each
case timeline. Activation refuses a table whose effective date is in the
future, because superseding the current one would otherwise leave no table in
force at all and every quote needing duty would fail to price.

## 5. Where state lives

| Record | What it is for |
|---|---|
| `Case` | The request. Carries the lifecycle status and the customer's trade terms. |
| `CaseMessage` | Every email in and out. The sender's own message identifier is unique, which is what makes intake repeat-safe. |
| `QuoteVersion` / `QuoteLine` | A priced quote. A revision creates the next version; unchanged lines are carried over with their prices intact. |
| `Clarification` | One question, the attribute it settles, and the answer read back into a value. |
| `Approval` | One decision a named role has to make. Re-priced numbers re-open it. |
| `CaseEvent` | The timeline: every step, who or what did it, how long it took, which engine, and what it cost. |
| `AuditEntry` | Who changed what. Separate from the timeline, which is the story. |

`QuoteLine` keeps two copies of the customer's words: `request_text`, which
grows as answers are folded in, and `original_request_text`, which never
changes. Comparing two versions of a request uses the original, or a line the
customer *clarified* looks like a line the customer *rewrote*.

## 6. Answers, in any language

A question records which attribute it settles. When the answer arrives,
`clarify.interpret_answer` reads it into a value for that attribute — in English
or in Traditional Chinese — and stores it on the line as a resolved attribute.
Matching then applies resolved attributes over whatever the written line says.

This matters more than it sounds. An earlier build appended the answer text to
the line and re-read it; a Chinese answer to an English line left the line
exactly as unclear as before, and the case could never finish. A reply that
names a line number can settle several questions about that line at once, which
is how people actually write.

## 7. What is deliberately not here

* **No vector database.** Eighteen thousand parts fit in memory, the scoring is
  explainable on screen, and it is one fewer service that can be down.
* **No queue or worker.** The agent's own working time is under a second for
  forty lines. Waiting happens on *people*, and that is modelled as case state,
  not as a job.
* **No password or token library.** Sign-in is pbkdf2 and hmac from the standard
  library. A demonstration that will not start because a dependency failed to
  compile is a demonstration that does not get shown.
* **Floats, anywhere near money.** `Decimal` throughout, stored as exact text
  through a SQLAlchemy type decorator so SQLite and PostgreSQL behave the same.

## 8. Running it serverless

Both halves deploy to Vercel as one project: `vercel.json` declares them as two
services behind one URL, `/api/*` to the backend. Serverless is a different environment and the
product checks for it rather than hoping: `settings.is_serverless` switches the
data load from a background thread to inside the request (a thread does not
outlive the invocation that started it), drops connection pooling for a null
pool (a pooled connection to a frozen function is a connection the database
holds open for nobody), moves generated documents to `/tmp`, and recommends the
smaller catalogue so a cold start does not spend seconds rebuilding the search
index from a remote database. If the database is still SQLite (the zero-setup
default), the first request after a start fills it with the demonstration data
(`app/bootstrap.py`, once per process, behind a lock) and every screen says
the data resets when the server restarts.

See [deploying-to-vercel.md](deploying-to-vercel.md).

## 9. What would change for production

1. **PostgreSQL with row-level security.** The connection is one environment
   variable and the deployment already requires it; the row-level policies are
   the work.
2. **A real mailbox.** Intake takes a message identifier, a sender, a body and
   attachments; a mailbox watcher is an adapter, not a redesign.
3. **The business system.** Stock, contracts and customers are read through
   `services/` functions that a real integration replaces one at a time.
4. **Prompt and model versioning in the release.** The evaluation harness is
   here; gating a deployment on its score is a pipeline step.
5. **The duty table owner's screen.** Loading a new version is an endpoint
   today; a real one needs an upload, a difference view and the broker's
   signature.
