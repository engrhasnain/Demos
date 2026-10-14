# Showing PortalBot

Ten minutes. The whole demonstration is three moments: it works, you kill it
and it does not book twice, and the portal changes under it and it stops.

Lead with the second and third. Everyone can imagine the first.

---

## Before they arrive

```bash
python backend/scripts/walkthrough.py
uvicorn app.main:app --reload --port 8004 --app-dir backend
cd frontend && npm run dev
```

Open <http://127.0.0.1:3004> and sign in as
`tomas.reyes@hengtai-industrial.example` / `demo1234` — operations lead, so
the evidence screen is open. You will switch to the developer account once,
near the end.

Leave it on **Control**.

---

## 0 · Frame it in one sentence (30 sec)

> "The carrier has no API for us and the business system has no way to write
> into it. A clerk does this by hand every morning: book each shipment in the
> portal, copy the tracking number, paste it into the old screen. About a
> hundred and eighty of them."

Then, before you run anything:

> "Driving somebody else's screen cannot be made unbreakable. I'm not going
> to claim it is. What I'll show you is that it knows when it's broken."

---

## 1 · A normal morning (1 min)

Press **Run**.

It works through the day's shipments. Watch the counters: booked, tracking
collected, written back, done. Nineteen stop with a named exception.

> "A hundred and sixty-one went through untouched. Nineteen stopped, and each
> one has a name on it — not 'error', a name."

Open one exception. Then open any shipment and show the trace: every step,
every attempt, what the portal said back.

---

## 2 · Kill it (3 min) — the first moment that matters

> "Now the honest question. What happens when this dies half way through?
> Because it will — the container restarts, the network drops, somebody
> deploys."

Press **Run, then kill it**. It stops after 25, as though the process was
killed.

Point at the queue. Some rows are `booked` with no tracking number. Some are
`booked` with tracking but not written back.

> "Every row says how far it got. That's the entire recovery design — the row
> is the transaction, because nothing spans a carrier portal and a legacy
> screen. There's no distributed transaction to have."

Press **Run** again.

> "There is no resume mode in this product. That's deliberate. A code path
> that only runs after a crash is a code path nobody has tested, and it'll be
> wrong on the morning you need it. A second run *is* the recovery path — same
> code, exercised every single run."

Now the payoff. Go to **Evidence** and point at the duplicates row, or say it
directly:

> "Nothing got booked twice. Two reasons, because one isn't enough. The
> idempotency key is *derived* from the shipment, not generated — the same
> shipment computes the same key on every machine on every run. Most libraries
> generate one, and a new key every attempt is exactly what books twice.
>
> And before booking, it asks the carrier whether that reference is already
> there. Our state can be lost. Theirs can't."

If the room is technical, add:

> "The test kills the run five times at different points, then checks the
> *carrier's* books — not ours. Checking our own records would prove nothing;
> the whole failure is the two sides disagreeing."

---

## 3 · The portal changes (3 min) — the second moment that matters

Sign out. Sign in as `ana.silva@hengtai-industrial.example` — developer.

Release portal **v2**. Two fields get renamed.

Press **Run**.

It halts. Before sending anything. The flag names which two fields moved.

> "This is the one that decides whether this kind of automation is worth
> having. The script stores the shape of the form it was written against and
> checks it before every run."

Then the argument, slowly, because this is the thing they will repeat to their
own team:

> "The industry answer to a changed page is fuzzy matching — 'self-healing'
> scripts that adapt and keep going. It's the wrong trade, and here is why.
>
> A bot that stops at nine in the morning costs one clerk one morning.
>
> A bot that carries on against a changed page, puts the postcode in the
> weight field, and books a hundred and eighty shipments to the wrong
> addresses costs a week and a lot of apologising.
>
> Self-healing turns the first into the second. It optimises for 'the run
> completed' when the goal is 'the shipments are right'."

Then:

> "Nothing here rewrites a script. A person reads the diff, because a person
> is the only one who can say whether a field called `receiver name` means
> what the field called `consignee` meant."

Acknowledge the change as the developer, and run again. It proceeds.

---

## 4 · The dangerous goods table (1 min)

Find the shipment that stopped on a missing declaration.

> "A part that reads as dangerous and isn't in the table stops the run. No
> inference, no nearest match, no default."

Then the reason, which lands better than the rule:

> "A UN number is a legal declaration. The wrong one can ground an aircraft,
> void the insurance and fine the shipper. A system that's ninety-five per
> cent right about UN numbers commits an offence about once a fortnight.
> That's not a good score — it's a compliance problem wearing a good score."

If asked: `UN3480` is loose lithium cells, `UN3481` is cells in equipment.
Separate entries, not interchangeable, because they are not interchangeable in
law.

---

## 5 · The nasty one (1 min)

Find a write-back exception caused by truncation.

> "The business system silently truncates anything over eighteen characters.
> The write *succeeds*. It returns fine. The tracking number is simply wrong
> from character nineteen onwards, and nobody finds out until a customer rings
> about a parcel they can't track.
>
> So the bot reads every value back after writing it. Nothing else catches
> this — there's no error to catch."

---

## 6 · The evidence (1 min)

**Evidence**, run it.

| Criterion | Bar | Result |
|---|---|---|
| Clean shipments automated | ≥95% | **100%** (161 of 161) |
| Duplicates after killing the run | 0 | **0** across 5 kills |
| Every exception classified and traceable | 100% | **100%** (19 of 19) |
| The portal changing is noticed | 100% | **stopped before sending anything** |

Pre-empt the obvious objection to the first row:

> "That's measured over the clean shipments. The nineteen awkward ones are
> excluded on purpose and counted in row three. I could give you one
> ninety-eight per cent number covering both — it'd be the nicer number and
> the less useful one, because it would hide whether the exceptions were
> handled or just rare."

---

## Questions you will be asked

**"Why not just use the carrier's API?"**
Use it. This product is for systems that do not have one. If they have an
API and this is still on the table, somebody has made a mistake.

**"Will it hit 100% on our carrier?"**
No promise. That figure is against a simulated portal built to fail in the
documented ways — rate limits, one-time codes, async booking, renamed fields.
A real portal will have failure modes nobody wrote down, and the first month
is finding them. What transfers is the structure: checkpoints on the row, a
derived key, a fingerprint check before sending, named exceptions.

**"What happens when it needs a one-time code?"**
It pauses and pushes to whichever clerk is on duty, with a fifteen-minute
window. Image challenges it does not attempt at all — getting past a
human-presence check is doing something the carrier has explicitly asked us
not to do.

**"How much maintenance is this?"**
Honestly: a change to the portal means a developer reads a diff and updates a
script. The product's job is to make sure that happens on the morning of the
change, with nothing sent, rather than three days later with a hundred
shipments to unpick.

**"Could it be made to adapt automatically?"**
Yes, and it should not be. That is the one design position in this product I
would argue about in a meeting.
