# Showing StockSense

Eight minutes. Sign in as **Tomas Reyes, Purchasing manager** — he can do
everything in this script except reload the catalogue.

---

## Before they arrive

```bash
python backend/scripts/walkthrough.py          # full 18,000 parts, about a minute
uvicorn app.main:app --reload --port 8002 --app-dir backend
cd frontend && npm run dev
```

Open <http://127.0.0.1:3002>, sign in, press **Work out this week**, leave it
on **The desk**.

---

## 1 · The desk (1 min)

> "Eighteen thousand parts. The engine looked at all of them this morning
> and found about twelve hundred worth buying, inside a six million dollar
> cash cap."

Point at the four figures, then the panel on the right.

> "And it has a date for you. Your mainland suppliers stop taking orders for
> the new year on the nineteenth of December. That is seventy-five days, and
> you need twelve weeks of cover on the shelf before it."

---

## 2 · What the catalogue is actually like (1 min)

Scroll to the pattern bars.

> "Four parts in five sell nothing most weeks, then forty at once. That is
> why the spreadsheet does not work, and it is why one forecasting model for
> everything does not either. Each of these gets a different method."

---

## 3 · One part, end to end (2 min)

Open **To order**, click any line.

> "Two years of sales. The red bars are weeks the shelf was empty — that is
> not zero demand, that is demand we could not see, and if you feed it back
> in as zero the forecast falls and you run out more often. The amber bar is
> a one-off project order, kept out of the baseline."

Scroll to the fan.

> "We never show one number. The band is what the last two years actually did
> over a lead time. The dashed line is where you reorder; the solid one is
> what you have."

Scroll to **How the quantity was reached**.

> "Nine steps, each with its arithmetic. Including this one — the supplier
> quotes twenty-eight days and takes thirty-five. We use thirty-five."

---

## 4 · The dead stock (1 min)

Back to **To order**, filter **Nothing to do**, find a *Not moving* line.

> "Nobody flagged this. The engine found it: stock on the shelf, nothing sold
> in six months."

> "The standard method for occasional demand is Croston, and Croston only
> updates in the weeks something sells. So a part that dies keeps the rate it
> had on its last sale, for ever, and you reorder it for ever. On this part
> Croston still says eight and a half a week. We say under one."

---

## 5 · The evidence (2 min) — the one that closes it

Open **Evidence**, press **Replay the year**.

> "This is not a slide. It just ran the last twelve months twice: once with
> the orders your buyers actually placed, once with ours. Same demand, same
> opening stock, same lead times. And at any week it is only allowed to see
> the weeks before it."

Walk the four bars, then the two charts.

> "Three quarters fewer stock-out weeks, on a quarter less money. You can
> always have one of those by giving up the other. Both at once is the thing
> worth paying for."

Scroll to the last panel.

> "And here is the part most tools would never show you. On the standard
> accuracy measure, a forecast that just says *zero* beats ours on
> seventy-nine per cent of your parts — because zero is the most common
> answer. It would also empty your warehouse. That is exactly why we do not
> grade this on accuracy. We grade it on stock-outs and money."

---

## 6 · The cash cap (1 min)

Open **To order**, filter **Held over**.

> "Six hundred lines it wanted and did not buy. Not the cheapest ones — the
> ones that do least good per dollar. The cheap part that stops a line gets
> bought before the expensive one that is merely comfortable."

> "And these were dropped for a different reason: the supplier has a hundred
> thousand minimum and the surviving lines did not reach it. Half a minimum
> order is not a cheaper order, it is a rejected one."

---

## If they ask

**"What model is this?"** None, for the numbers. The forecasting is ordinary
statistics, written out and visible — no key, no account, no network, no
cost. A language model, if one is configured, only ever writes words.

**"Our buyers are better than that."** Then the replay will say so, and it
will say so on your data, not ours. That is the point of it being a replay
rather than a claim.

**"Our carrying cost is not twenty per cent."** Nobody's is exactly anything,
which is why it is a range here and a setting, not a number baked into the
code.

**"What about the parts that are genuinely new?"** They borrow the shape of
their family, the range is widened by half again, and the screen says so on
the part. A part with two years of history and no sales does not borrow — it
is not new, it is unwanted.

**"How long to connect our system?"** The engine needs three things per part:
sales by week, what is on hand and on order, and the supplier's delivery
dates. Everything else it works out.
