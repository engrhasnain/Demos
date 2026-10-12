# Showing LedgerFlow

Eight minutes. Sign in as **Ravi Menon, Controller** — he can do everything in
this script except load the data.

---

## Before they arrive

```bash
python backend/scripts/walkthrough.py
uvicorn app.main:app --reload --port 8001 --app-dir backend
cd frontend && npm run dev
```

Open <http://127.0.0.1:3001>, sign in, leave it on **The desk**.

---

## 1 · The desk (1 min)

> "Nineteen documents came in this morning. Ten are already in the ledger.
> Nobody touched them."

Point at the four figures. Then the queue on the left — worst first, red before
amber.

> "These are the ones that stopped. Each one says why in three words."

---

## 2 · Only what arrived (1 min)

Open the invoice headlined **"Only part of it has arrived"**.

> "They billed for the whole order. Part of it turned up."

Press the held amount. The panel shows the arithmetic: delivered to date, less
what was already billed, times the price, with the goods receipt it came from.

> "We pay for what arrived. The rest is held, not refused — the goods may
> still come."

---

## 3 · The repeat (1 min)

Open the one headlined **"Already received"**.

> "This is an invoice we already have. They sent it again as a reminder, with
> the number written differently and a day on the date."

Show the exception detail: what it matched and on which signal.

> "Five signals, not one. The number alone misses most of them."

---

## 4 · The bank change (2 min) — the one they care about

Open the one headlined **"Bank details changed"**. Nothing is payable.

> "An invoice turned up asking to be paid into an account we have never paid.
> That is the most expensive thing that happens to a finance team."

Follow **Make the call-back** to the supplier.

> "Three things happened and none of them was a change. The invoice is
> blocked. So is every other invoice from this supplier. And there is a
> call-back — to the number we already had, not the one on the invoice."

Type a note, press **They confirmed it**.

> "Now, and only now, the account changes, and what was stuck moves."

Show the released invoice.

---

## 5 · Paid twice (2 min) — the one the controller asks about

Open an invoice that is ready to post. Press **Post, but drop the connection**.

> "The ledger took the bill. Then the connection died before it told us. This
> is the window where careless retries pay suppliers twice."

Read the line: *bills in the ledger: 1*. Now press **Post it**.

> "Posted. Still one bill. Each invoice has a key — a hash of the entity,
> supplier, number and amount — and the second attempt found the bill the
> first one had already written."

Go to **Ledger** and show one line, not two.

---

## 6 · Evidence (1 min)

Open **Evidence**, press **Measure it now**. About fifteen seconds.

> "This is not a slide. It just put 180 documents with known right answers
> through the same code you have been watching, and dropped the connection
> thirty-odd times."

Walk the six bars. Point at the misses list.

> "It shows you what it got wrong too. A number without its misses is marketing."

---

## If they ask

**"What model is this?"** None, by default. The reading is deterministic code:
no key, no account, no network, no cost. An external model can be switched in
behind the same strict schema, and the figures are still checked by code either
way.

**"What if it reads something wrong?"** Then the arithmetic check or the
three-way match disagrees and it stops. The reading step is never the last word
on a number.

**"Can it post the wrong amount?"** Every amount is an exact decimal from the
document to the ledger — no floating point anywhere, and the API sends amounts
as strings so JSON cannot round them. Press any figure to see the working.

**"What happens on a bad day?"** Nothing posts that should not. The failures
are refusals, not silent errors, and every refusal names the rule.

**"How long to connect our ledger?"** The posting step is one adapter with two
operations: find a bill by key, write a bill. The rest does not change.
