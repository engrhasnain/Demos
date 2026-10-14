# PortalBot

**Books every shipment in a carrier portal and writes the tracking number
back into a legacy screen — two systems with no way in but the screen —
without duplicates, and without silently doing the wrong thing when the
portal changes.**

One of six products built for the same distributor. This is the one for
systems that cannot be integrated with at all — where the only way in is the
screen a person would use.

A working product — FastAPI backend, Next.js interface, both deploying to
Vercel.

---

## Run it

```bash
# backend  →  http://127.0.0.1:8004
pip install -r backend/requirements.txt
python backend/scripts/walkthrough.py
uvicorn app.main:app --reload --port 8004 --app-dir backend

# interface →  http://127.0.0.1:3004
cd frontend && npm install && npm run dev
```

Sign in at <http://127.0.0.1:3004>, password `demo1234`.

> Ports 3004 and 8004, so this runs alongside the other four MVPs.

---

## The thesis

**An automation driving somebody else's screen cannot be made unbreakable.
It can be made to know when it has broken.**

The screen is not yours. It changes when they ship, and no cleverness in
the selectors makes that untrue. The documented dominant failure in this
kind of work is a changed selector — and the usual answer to it, fuzzy
matching and "self-healing", makes the *expensive* failure more likely
rather than less.

Because stopping is cheap. A bot that stops at nine in the morning costs
one clerk one morning. A bot that carries on against a changed page, puts
the postcode in the weight field and books a hundred and eighty shipments
to the wrong addresses costs a week and a lot of apologising. Self-healing
turns the first failure into the second.

So the script records the shape of the form it was written against, every
run checks that shape first, and a mismatch stops the run and raises a
flag. **Nothing rewrites a script.** A person reads the diff, because a
person is the only one who can say whether the new field means what the
old one did.

> On the much-quoted "30 to 50 per cent of RPA projects fail": that figure
> traces to consulting commentary rather than an instrumented study, and
> this README is not going to repeat it as though it were measured. The
> *mechanism* is well documented, and it is the one above.

---

## Two systems, no transaction

The booking happens in the carrier's portal. The write-back happens in the
business system. Nothing spans the two, so the row is the transaction:

```
pending ──book──▶ booked ──collect──▶ booked+tracking ──write──▶ written_back ──▶ done
```

Kill the process anywhere along that line and the row says how far it got.
The next run reads the row and carries on. There is no separate "resume"
mode, because a code path that only runs after a crash is a code path
nobody has tested — **a second run *is* the recovery path.**

The key is **derived from the shipment**, not generated: the same shipment
computes the same key on every machine on every run. A generated key is a
new key every attempt, which is exactly what books twice.

And before booking anything, it asks the carrier whether that reference is
already there. Local state can be lost; the carrier's cannot.

---

## Measured, not claimed

| Criterion | Bar | Result |
|---|---|---|
| Clean shipments automated | ≥95% | **100%** (161 of 161) |
| Duplicates after killing the run | 0 | **0** across 5 kills |
| Every exception classified and traceable | 100% | **100%** (19 of 19) |
| The portal changing is noticed | 100% | **stopped before sending anything** |

```bash
python backend/scripts/walkthrough.py --evaluate
python -m pytest backend/tests          # 49 tests
```

The kill test is the one worth watching: it stops the run part way
through, repeatedly, at different points, then checks the **carrier's own
books** for a reference booked twice.

---

## The two systems are real, not mocked

`systems/carrier.py` and `systems/legacy.py` are small stateful systems
with their own rules, and the bot drives them as it would drive the real
ones. Everything the automation copes with is in there because those
systems do it:

**The carrier portal** rejects a weight that does not match its packages,
refuses an aerosol with no declaration and a declaration with a malformed
UN number, rate limits, goes slow, falls over, demands a one-time code,
books asynchronously so the tracking number is not in the response, and
can ship a new version that renames two fields.

**The business system** locks a record while somebody has it open, refuses
a write against a revision it has moved past, is case sensitive on write
and not on read, and **truncates anything over eighteen characters without
saying so**. That last one is the nastiest, because it succeeds — so the
bot reads the value back and treats a silent truncation as an exception.

---

## The hard cases

| Case | What happens |
|---|---|
| Two systems, no connection | Each one its own checkpoint on the row |
| Killed part way | The row says where it got to; the next run resumes |
| Duplicates | A key derived from the shipment, plus asking the carrier first |
| Dangerous goods | A table keyed on the **part**. A part that reads dangerous and is not in it **stops the run** |
| Addresses | Validated and tidied before the portal sees them; a four-digit Taiwan postcode is refused, not guessed |
| One-time codes | It pauses and pushes to the clerk on duty. Image challenges are never attempted |
| Slow or down | Exponential backoff with jitter, then an exception with a name |
| Delayed results | Polled with a timeout, not a guessed sleep |
| The portal changes | The run stops, a flag is raised, and the script is never rewritten |

### Why a UN number is never guessed

A UN number is a legal declaration. The wrong one is not a data error to
be corrected later — it can ground an aircraft, void the insurance and put
a fine on the shipper. A system that is 95 per cent right about UN numbers
commits an offence once a fortnight.

So there is a table, it is keyed on the part number, and a part that is
not in it stops the run. There is no inference step, no nearest match and
no default. `UN3480` (loose cells) and `UN3481` (cells in equipment) are
different entries and are not interchangeable.

---

## Who may do what

| Role | May |
|---|---|
| Shipping clerk | Run the bot, supply a one-time code |
| Operations lead | Also run the evidence |
| Developer | Also acknowledge a changed form, and release a new portal version in the demonstration |
| Administrator | Load a day |

---

## Try it in the interface

- **Run** — a normal morning.
- **Run, then kill it** — stops after 25, as though the process died. Press
  **Run** again: nothing is booked twice.
- Sign in as the developer and release portal **v2** — the next run halts
  before sending anything and tells you which two fields moved.

---

## Deploying to Vercel

**Backend** — root `backend`. Set `DATABASE_URL` (PostgreSQL), `JWT_SECRET`,
`CORS_ORIGINS`. It refuses to start outside a demo on the published secret.

**Interface** — root `frontend`. Set `NEXT_PUBLIC_API_URL`.

> The simulated portal lives in the process, so on serverless it resets
> when the function does. The state screen says so rather than pretending.

---

## Settings

| Variable | Default | What it does |
|---|---|---|
| `MAX_ATTEMPTS` | 4 | Retries before a step becomes a named exception |
| `BACKOFF_SECONDS` | 0.01 | Doubled each attempt, with jitter |
| `TRACKING_TIMEOUT_SECONDS` | 2 | How long to poll before leaving it for the next run |
| `CHALLENGE_MINUTES` | 15 | How long a clerk has to supply a code |
| `CARRIER_NAME` | Hsinchu Logistics | Which carrier the write-back records |

---

## Layout

```
backend/
  app/
    systems/       the carrier portal and the legacy screen, as they behave
    domain/        the dangerous goods table, the drift detector
    services/      the bot, the run, address checking
    evaluation/    the acceptance criteria, including the kill test
    seed/          a day's shipments with the awkward ones in proportion
  tests/           49 tests
frontend/
  src/app/         control, one shipment with its whole trace, evidence
```


---

## Further reading

- [`docs/how-it-decides.md`](docs/how-it-decides.md) — the thesis, the
  correctness argument for crossing two systems, and what this product does
  not claim.
- [`docs/demo-script.md`](docs/demo-script.md) — ten minutes, in order.
