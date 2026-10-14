# LedgerFlow

**Supplier invoices read, checked against the purchase order and the delivery,
and posted to the ledger. It stops when something is wrong, and it says why.**

One of six products built for the same distributor. This is the one that
shows a process crossing two systems that share no transaction, and staying
correct when it is interrupted half way.

A working product — FastAPI backend, Next.js interface, both deploying to
Vercel. No key, no account, no external service required.

---

## Run it

Two terminals, from this folder.

```bash
# backend  →  http://127.0.0.1:8001
pip install -r backend/requirements.txt
python backend/scripts/walkthrough.py          # loads the data and proves it works
uvicorn app.main:app --reload --port 8001 --app-dir backend

# interface →  http://127.0.0.1:3001
cd frontend && npm install && npm run dev
```

Open <http://127.0.0.1:3001>. Sign in as anybody on the list; the password is
`demo1234`. What you are allowed to do depends on who you pick.

> Ports 3001 and 8001, not 3000 and 8000, so this runs alongside QuoteAgent.

If you skip the walkthrough, the first screen offers to load the data and run
the batch for you.

---

## What it does

An invoice arrives. LedgerFlow:

1. **Reads it** — header fields and every line, on every page.
2. **Checks the arithmetic** — lines add to the net, 5% business tax, net plus
   tax equals the total.
3. **Checks who it is for** — the buyer's business number has to be ours, and
   the right legal entity.
4. **Checks it is not a repeat** — five separate signals, not just the number.
5. **Matches it three ways** — purchase order, cumulative goods receipts,
   invoice. You pay for what arrived, not for what was ordered.
6. **Converts the currency** at the rate for the invoice date.
7. **Posts it**, if nothing needs a person. Otherwise it stops and says why.

Three things stop it dead, whatever else is true:

| Stop | Why |
|---|---|
| A bank account that is not the one on file | A call-back to the number already on file is the only way to change it. The invoice cannot change it. |
| An invoice already received | Five signals: the file, the supplier and number, the supplier and amount in a date window, the number alone, the order and amount. |
| An invoice billed to somebody else's business number | We cannot claim the tax, so we cannot post it. |

---

## The parts that matter

**Money is exact.** Every amount is a `Decimal`, stored as text. There is no
float anywhere between the document and the ledger, and the API sends amounts
as strings so JSON cannot round them.

**Every figure opens.** Press any number on screen and the arithmetic slides
out: each step, the formula, and the record every input came from. Nothing
goes to the ledger that a controller cannot take apart.

**Posting is retry-safe.** Each invoice has an idempotency key — a hash of the
entity, supplier, number, amount and currency. If the ledger takes the bill and
the connection then dies, posting again lands on the same bill. There is a
button in the interface that reproduces exactly that failure, on a real
invoice, so you can watch it not pay twice.

**The reading engine is deterministic.** No key, no account, no network, no
cost. Setting `MODEL_API_KEY` and `MODEL_BASE_URL` switches the reading step to
an external model held to the same strict schema; everything else is unchanged,
and the figures are still checked by code. Nothing a model returns is trusted
without being checked.

**Taiwan uniform invoices are first class.** Two letters and eight digits, the
weighted checksum on the unified business number including the post-April-2023
rule, and the square barcode decoded as data. When the barcode is readable, it
outranks the text on the page.

---

## Proving it

```bash
python backend/scripts/walkthrough.py          # the batch, with nine checks
python backend/scripts/walkthrough.py --evaluate
python -m pytest backend/tests                 # 78 tests
```

The **Evidence** screen runs the same measurements from the interface. Each one
puts documents with a known right answer through the real pipeline and reports
what it got, including what it got wrong.

Measured on 180 generated documents and 34 dropped connections:

| What is measured | Bar | Measured |
|---|---|---|
| Header fields read right | ≥ 98% | 100% (960 of 960) |
| Line figures read right | ≥ 94% | 99.6% (887 of 891) |
| Planted repeats caught | 100% | 100% (40 of 40) |
| Planted bank changes blocked | 100% | 100% (20 of 20) |
| Clean invoices posted untouched | ≥ 60% | 81.7% (98 of 120) |
| Bills paid twice after a crash | 0 | 0 |

The measurement runs inside a savepoint and is rolled back, so it does not
leave test invoices behind.

---

## The demonstration batch

Nineteen documents, each chosen because it breaks a prototype. Eight ordinary
invoices that should post on sight, and eleven that should not:

| Document | What it is there to show |
|---|---|
| Eight ordinary invoices | They reach the ledger with nobody touching them |
| A photograph from a telephone | Crooked, widely spaced text still reads |
| A paper uniform invoice | The Taiwan layout and the business tax |
| An electronic uniform invoice | The square barcode outranks the page |
| A four-page forwarder statement | Every page read, subtotals reconciled |
| Billed in full, part delivered | Only what arrived is payable |
| The same invoice as "0042" | Caught as a repeat despite the disguise |
| A new bank account | Hard stop and a call-back to the number on file |
| A credit note | Not three-way matched; linked to the original |
| The wrong business number | Refused: it is not billed to us |
| Freight not on the order | Accepted, because it is inside the allowance |
| An invoice in dollars | Converted, both figures kept |

---

## Who may do what

| Role | May |
|---|---|
| Clerk | Upload, read, run the batch |
| Accountant | Clear exceptions, sign, post, reject |
| Controller | All of the above, plus record the telephone call that changes a bank account, and read the audit trail |
| Finance director | The second signature above the two-step limit |
| Administrator | Load the data |

A second signature always has to come from somebody other than the first.

---

## Deploying to Vercel

Two projects from this one repository.

**Backend** — root directory `backend`. It is already set up: `vercel.json`
points at `api/index.py`, which exports the same application. Set:

| Variable | Value |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://…` — required; a serverless function has no disk that survives |
| `JWT_SECRET` | anything long and random |
| `CORS_ORIGINS` | the interface's URL |

**Interface** — root directory `frontend`. Set `NEXT_PUBLIC_API_URL` to the
backend's URL.

Without `DATABASE_URL` the backend still runs, on SQLite in the function's
scratch space, and the first screen says so: the data goes away when the
function does.

---

## Settings

| Variable | Default | What it does |
|---|---|---|
| `DATABASE_URL` | SQLite in `backend/var` | Where the data lives |
| `JWT_SECRET` | a demonstration value | Signs sign-in tokens |
| `AUTO_POST_CEILING_TWD` | 200,000 | Above this, somebody signs |
| `TWO_STEP_APPROVAL_TWD` | 1,000,000 | Above this, two people sign |
| `DEFAULT_TOLERANCE_PERCENT` | 2 | How far above the order a price may sit |
| `DEFAULT_UNORDERED_ALLOWANCE_TWD` | 1,000 | Charges not on the order, accepted |
| `MODEL_API_KEY`, `MODEL_BASE_URL` | empty | Switches the reading step to an external model |

---

## Layout

```
backend/
  app/
    domain/        Taiwan uniform invoices, business numbers, the barcode
    services/      reading, matching, guards, approvals, posting, the pipeline
    routers/       the HTTP surface
    evaluation/    the acceptance criteria, as code
    seed/          the generated company and the demonstration batch
  api/index.py     the Vercel entry point
  scripts/         the walkthrough
  tests/           78 tests
frontend/
  src/app/         desk, invoices, suppliers, ledger, evidence
  src/components/  the component kit and the figure panel
```


---

## Further reading

- [`docs/how-it-decides.md`](docs/how-it-decides.md) — every rule, in the
  order it runs, and what this product does not claim.
- [`docs/demo-script.md`](docs/demo-script.md) — eight minutes, in order.
