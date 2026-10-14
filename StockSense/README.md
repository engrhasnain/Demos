# StockSense

**What to reorder, how much, and what it would cost to be wrong — for
eighteen thousand parts that mostly sell nothing, from suppliers that mostly
run late, around a shutdown that closes half of them for six weeks.**

One of six products built for the same distributor. This is the one that
shows a forecast being made, and then being argued with: the statistics are
the easy half, and knowing when the statistics are lying is the product.

A working product — FastAPI backend, Next.js interface, both deploying to
Vercel. No key, no account, no external service.

---

## Run it

Two terminals, from this folder.

```bash
# backend  →  http://127.0.0.1:8002
pip install -r backend/requirements.txt
python backend/scripts/walkthrough.py --small    # loads the data and proves it works
uvicorn app.main:app --reload --port 8002 --app-dir backend

# interface →  http://127.0.0.1:3002
cd frontend && npm install && npm run dev
```

Open <http://127.0.0.1:3002>. Sign in as anybody on the list; the password is
`demo1234`.

> Ports 3002 and 8002, so this runs alongside QuoteAgent and LedgerFlow.
> Drop `--small` for the full 18,000 parts; it takes about a minute.

---

## The problem

Two buyers manage eighteen thousand parts from spreadsheets. Four things make
that hard, and all four are in here:

**Most parts sell nothing most weeks.** Four in five are occasional or lumpy:
nothing for a month, then four hundred. Ordinary forecasting handles this
badly, and the ordinary *measure* of forecasting handles it worse — see below.

**Suppliers slip.** A quoted twenty-eight days that is really thirty-five is
a week of stock nobody budgeted for. The quote is recorded and then ignored;
what gets used is the distribution of what actually happened.

**The shelf being empty hides demand.** A week that sold nothing because
there was nothing to sell is recorded as a week nobody wanted any. Feed that
back in and the forecast falls, so you order less, so the shelf is empty more
often. Parts that run out keep running out.

**Lunar New Year.** In 2027 it falls on 6 February. Taiwan closes for about a
week. Mainland China is disrupted for six, and most plants stop taking orders
for the period by **19 December** — seventy-five days before the holiday. An
order placed after that does not ship late, it does not ship.

---

## The argument this product makes

Forecast accuracy is the wrong thing to measure, and StockSense says so on
its own evidence screen.

Absolute error is smallest at the median. The median of a series that is zero
four weeks in five is **zero**. So on the standard measure, a forecast that
always predicts nothing beats a real one — on **79%** of this catalogue's
parts, measured, not asserted. It would also empty the warehouse.

So StockSense is not graded on accuracy. It is graded by replaying the last
twelve months twice — once with the orders the buyers actually placed, once
with the orders it would have recommended — against the same demand, the same
opening stock and the same lead times, and counting stock-out days and money.

---

## What it does

1. **Classifies** every part by how often it sells and how evenly, using the
   published cut-offs (interval 1.32, variability 0.49).
2. **Cleans the history**: lifts weeks when the shelf was empty, strips
   one-off project orders, splices a replaced part's history onto its
   successor.
3. **Forecasts** with the method that suits the pattern — exponential
   smoothing for steady parts, size-and-probability for occasional ones.
4. **Sizes the cover** from the part's own past rather than a bell curve,
   because occasional demand is not normally distributed and pretending it is
   buys far too much stock.
5. **Decides**, part by part: order, order early for the shutdown, hold over,
   or nothing to do.
6. **Fits it in the cash**, most urgent per dollar first, respecting supplier
   minimums.

### The methods, and why not Croston

| Method | Used for | Why |
|---|---|---|
| Exponential smoothing | Sells most weeks | Recent weeks weighted more |
| Croston | — | The classic for occasional demand, and the reason for the next two rows |
| Croston, bias corrected | available | Croston runs high; the published correction takes most of it out |
| **Size and probability** | **Occasional and lumpy** | **Updated every week, including the quiet ones** |

Croston only updates in the weeks that sell something, so a part that stops
selling keeps the rate it had on the day it died — for ever. Measured on this
catalogue, for a part with no sales in six months:

```
Croston would still say   8.59 a week
StockSense says           0.69 a week
```

That difference is the 22% of inventory value that has not moved in six
months. It is why the default here is not Croston.

---

## Proving it

```bash
python backend/scripts/walkthrough.py --evaluate
python -m pytest backend/tests          # 84 tests
```

The **Evidence** screen runs the same replay from the interface.

Measured on 2,000 parts over 52 weeks, against the buyers' own orders:

| | The buyers | StockSense |
|---|---|---|
| Stock-out weeks | 8,247 | **2,044** |
| Parts that ran out | 1,577 | **889** |
| Units not shipped | 8,402,271 | **1,480,295** |
| Average stock held | 48,143,730 | **35,032,162** |

| Acceptance criterion | Bar | Result |
|---|---|---|
| Stock-out weeks | fewer than the buyers | **pass** — 75% fewer |
| Inventory value | the same or lower | **pass** — 27% lower |
| Occasional parts | reported separately | **pass** — 1,713 of 2,000, reported on their own |
| Every recommendation explains itself | 100% | **pass** — 2,000 of 2,000 |

Fewer stock-outs *and* less money is a strict improvement on both axes; you
can always have one by sacrificing the other.

### The rule that makes the replay honest

At week W the engine may see weeks 0 to W−1 and nothing else. That slice
happens in exactly one place in `services/replay.py`, and a test pins it. A
backtest that lets the model see the answer will prove anything you like.

---

## The hard cases

| Case | What happens |
|---|---|
| Occasional demand | Classified, then forecast by a method meant for it |
| Project orders | Found and kept out of the baseline |
| The shelf was empty | Treated as unknown demand, not zero demand |
| Supersession | History carried from the old part number to the new |
| New parts | Forecast from the family, with a wider range and a flag |
| Variable lead time | Cover sized from the supplier's record, not the quote |
| Lunar New Year | Per-country calendars, with an order-by date and pre-build |
| Packs and minimums | Rounded up to whole packs; a supplier under its minimum is dropped whole |
| Dead stock | Found by the engine, not flagged by a human |

---

## Who may do what

| Role | May |
|---|---|
| Buyer | Read everything, build the week's plan |
| Senior buyer | Also run the replay |
| Purchasing manager | Also read the audit trail |
| Finance director | Everything above |
| Administrator | Load the catalogue |

---

## Deploying to Vercel

Two projects from this folder.

**Backend** — root directory `backend`. Already set up: `vercel.json` points
at `api/index.py`. Set:

| Variable | Value |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://…` — required; a function has no disk that survives |
| `JWT_SECRET` | anything long and random; it refuses to start without one outside a demo |
| `CORS_ORIGINS` | the interface's URL |

**Interface** — root directory `frontend`. Set `NEXT_PUBLIC_API_URL` to the
backend's URL.

---

## Settings

| Variable | Default | What it does |
|---|---|---|
| `WEEKLY_CASH_CAP_TWD` | 6,000,000 | What may be committed in one round |
| `CARRYING_COST_PERCENT_LOW` / `_HIGH` | 10 / 25 | What stock costs to hold, as a range because nobody knows it exactly |
| `REVIEW_PERIOD_DAYS` | 7 | How often orders are placed |
| `SERVICE_LEVEL_A` / `_B` / `_C` | 0.98 / 0.95 / 0.90 | Cover by how much the part matters |
| `PROJECT_SPIKE_MULTIPLE` | 6 | Above this, a week is a project order |
| `SHUTDOWN_PREBUILD_WEEKS` | 2 | Spare cover bought before a shutdown |
| `STOCKSENSE_TODAY` | the real date | Pins the day, for a recorded demonstration |
| `MODEL_API_KEY`, `MODEL_BASE_URL` | empty | A model may write words. It never writes a number. |

---

## Layout

```
backend/
  app/
    domain/        classification, the forecasting methods, cover, lead time,
                   the shutdown calendar, the scoring and its trap
    services/      cleaning history, demand, reorder, the cash cap, the replay
    routers/       the HTTP surface
    evaluation/    the acceptance criteria, as code
    seed/          the generated catalogue and two years of history
  api/index.py     the Vercel entry point
  scripts/         the walkthrough
  tests/           84 tests
frontend/
  src/app/         desk, to order, parts, suppliers, evidence
  src/components/  the kit, the charts, the figure panel
```


---

## Further reading

- [`docs/how-it-decides.md`](docs/how-it-decides.md) — how the forecast is
  chosen and argued with, and what this product does not claim.
- [`docs/demo-script.md`](docs/demo-script.md) — the demonstration, in order.
