# How StockSense decides

Every rule, in the order it runs. Nothing here is a model's opinion: every
quantity is produced by code, and the interface will show you the arithmetic
for any of them.

---

## 1. What kind of part is this?

Two numbers off the history:

- **Average demand interval** — weeks divided by weeks that sold something.
  1.0 means it sells every week.
- **Variability of size** — the squared coefficient of variation of the
  quantities that did sell.

Split at the published cut-offs, 1.32 and 0.49:

```
            variable │   Uneven sizes      Occasional and uneven
              sizes  │   (smoothing)       (size × probability)
                     │
            even     │   Steady            Occasional
              sizes  │   (smoothing)       (size × probability)
                     └──────────────────────────────────────────
                       sells most weeks    long gaps
```

Those cut-offs are not invented. They are where the error of one method
crosses the error of the other in the literature, which makes them the
numbers worth comparing against.

In this catalogue about four parts in five land on the right-hand side. That
is the whole difficulty, and it is why one model for everything does not work.

## 2. Clean the history before forecasting from it

Three corrections, each of which changes the answer.

**The shelf was empty.** A week with nothing to sell is not a week nobody
wanted any. Demand in those weeks is lifted to the rate seen in the weeks we
*could* sell — not to the maximum, because the honest estimate of what we
missed is the ordinary rate, not the best case. Without this, a part that
runs out is forecast lower, so less is ordered, so it runs out more. It is a
loop and it is self-reinforcing.

**A project came through.** One customer building a plant orders twenty
thousand once. A week more than six times the usual size, against a part that
normally sells far less, is not the usual trade. It is recorded, and kept out
of the baseline.

**The part replaced another.** The predecessor's weeks are spliced on before
the successor's own. Without it a supersession looks like a brand new part
and the forecast is useless for the better part of a year.

## 3. Forecast

| Pattern | Method | Why |
|---|---|---|
| Steady, uneven sizes | Exponential smoothing | Sells most weeks; recent weeks weigh more |
| Occasional, lumpy | Size × probability | See below |
| Nothing ever sold | Nothing | Two years of silence is an answer |

**Why not Croston.** Croston smooths the sizes and the gaps separately and
divides. It is the classic answer for occasional demand and it has one fatal
habit: it only updates in the weeks that sell something. A part that stops
selling holds the rate it had on its last sale, indefinitely. An ordering
engine built on it buys dead stock for ever.

Size-and-probability updates the probability **every** week, including the
quiet ones, so a part that stops selling decays towards zero. Measured here:

```
A part with no sales in six months
  Croston        8.59 a week      ← would keep ordering
  Bias-corrected 7.73 a week      ← also
  StockSense     0.69 a week
```

**New parts** with too little history of their own borrow the averaged shape
of established parts in the same family, with the range widened by half
again, and the screen says plainly that is what happened. A part that has
existed for two years and sold nothing does **not** borrow — it has had its
chance, and borrowing would be buying on somebody else's demand.

## 4. How long is the wait, really

Every supplier quotes a lead time. The quote is recorded and not used. What
is used is the distribution of what actually happened: the average, the
spread, the ninetieth percentile and the worst. The gap between the quote and
the average is usually the most persuasive figure on the supplier page.

With fewer than three deliveries on record there is no distribution, so the
quoted figure is used with a deliberately pessimistic spread. Not knowing is
a reason for more cover, not for optimism.

## 5. How much cover

The cover has to last the **lead time plus the review period**. If orders go
out on Mondays, a part that drops below its reorder point on Tuesday waits
six days before anybody looks at it.

Two ways of sizing it, and the choice matters:

**The textbook way**, used when there is too little history:

```
sigma over the cover = sqrt( L × sigma_d²  +  d² × sigma_L² )
safety stock         = z × sigma over the cover
```

The second term is the supplier's timing varying, and leaving it out is the
most common fault in a home-built spreadsheet. It is why a supplier that
slips two weeks empties a shelf that was "covered".

**The way used wherever there is enough history.** The textbook formula
assumes demand over the lead time is normally distributed. For a part that
sells 0, 0, 0, 400 it is not, and it fails expensively: the standard
deviation of a lumpy series is large, so `z × sigma` demands an enormous
buffer for a part that mostly needs none. That is how an inventory tool ends
up holding *more* stock than the buyers it replaced.

So the distribution is taken, not assumed. Slide a window the length of the
cover period along the past two years and total each window; that set of sums
is the distribution of demand over a lead time, with the real gaps and the
real spikes in it. The reorder point is the point below which it fell in 95
per cent of those windows. The window length is swept from a short lead time
to a long one, so the supplier's unreliability is in the windows rather than
bolted on.

On this catalogue that one change is the difference between failing the
inventory bar and passing it.

**Service level** is set by how much the part matters: 98 per cent for A, 95
for B, 90 for C.

## 6. The shutdown

Per country, because they are not the same event:

| | Taiwan | Mainland China | Vietnam |
|---|---|---|---|
| Closed | ~9 days | ~22 days | ~12 days |
| Disrupted in all | ~14 days | ~43 days | ~22 days |
| Stops taking orders | 21 days ahead | **49 days ahead** | 28 days ahead |

The test is not "is the cut-off close". It is: **on the last day we can
order, will what is on the shelf carry us through?** Projected position at the
cut-off, against the cover the shutdown needs. If it falls short, the order
goes out now, weeks before any reorder point would have asked for it.

For 2027 that means mainland orders have to be placed by **19 December 2026**,
and about twelve weeks of cover has to be on the shelf.

## 7. Make it an order somebody can send

Whole packs, never below the minimum order quantity, and **rounded up**.
Rounding an order down to save a few hundred dollars is how a part that was
going to be covered is not.

## 8. Fit it in the cash

Every reorder tool will happily recommend forty million on a week when there
is six million. What a buyer needs is the line through the list.

Lines are taken in order of **how much good each does per dollar** — urgency
divided by cost. Sorting by value buys the expensive things first and runs
out before the cheap part that stops a production line.

Urgency combines how much the part matters (A, B or C), how little cover is
left, and how far below the reorder point it already is. A pre-build for a
shutdown is weighted higher, because the chance does not come again.

Then **supplier minimums**: a supplier whose surviving lines do not reach the
order value they insist on is dropped whole and the money handed back, which
may let other lines in. Part of a minimum order is not a cheaper order, it is
a rejected one. This is checked whether or not the budget was tight.

---

## What each decision means

| Decision | Meaning |
|---|---|
| **Order** | Below the reorder point, and there is cash |
| **Order before the shutdown** | Will not survive the shutdown otherwise |
| **Not this week** | Wanted, but the cash ran out or the supplier minimum was missed |
| **Watch** | Covered, nothing selling, dead stock, or replaced |

Every one of them records the demand model it used, the lead time it used,
the cash it consumes and the full working. That is the fourth acceptance
criterion, and it is measured rather than promised.
