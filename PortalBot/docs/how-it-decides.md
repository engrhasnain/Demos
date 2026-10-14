# How PortalBot decides, and what it does not claim

Written for whoever has to decide whether automating against somebody else's
screen is a sensible risk. It sets out the thesis, the correctness argument
for crossing two systems, every decision the bot makes on its own, and the
places where this product's claim stops.

---

## 1. The thesis

> **An automation driving somebody else's screen cannot be made unbreakable.
> It can be made to know when it has broken.**

The screen is not yours. It changes when the carrier ships, and no amount of
cleverness in the selectors makes that untrue. The dominant failure mode in
this kind of work is a changed selector, and the industry's usual answer —
fuzzy matching, "self-healing" scripts — makes the **expensive** failure more
likely rather than less.

The argument is about which failure you would rather have:

| | Cost |
|---|---|
| The bot stops at nine in the morning | One clerk, one morning |
| The bot carries on against a changed page, puts the postcode in the weight field, and books 180 shipments wrong | A week, and a lot of apologising |

Self-healing converts the first into the second. It is optimising the metric
("the run completed") against the goal ("the shipments are right").

So: the script records the **shape of the form** it was written against. Every
run checks that shape before sending anything. A mismatch stops the run and
raises a flag. **Nothing rewrites a script, ever.** A person reads the diff,
because a person is the only one who can say whether a field that got renamed
still means what the old one meant.

### On the figure everyone quotes

You will hear that 30–50% of these projects fail. That number traces to
consulting commentary, not to an instrumented study, and this document is not
going to repeat it as though it were measured. The *mechanism* above is well
documented and is the one that matters.

---

## 2. Crossing two systems with no transaction

The booking happens in the carrier's portal. The write-back happens in the
business system. Nothing spans the two — there is no distributed transaction
available and there never will be.

So **the row is the transaction**:

```
pending ──book──▶ booked ──collect──▶ booked+tracking ──write──▶ written_back ──▶ done
```

Kill the process anywhere along that line and the row says how far it got.
The next run reads the row and carries on from there.

There is deliberately **no separate resume mode**. A code path that only runs
after a crash is a code path nobody has tested, and it will be wrong on the
morning it is needed. Here, a second run *is* the recovery path — it is the
same code, exercised every single run.

### Why it does not book twice

Two independent reasons, because one is not enough:

1. **The idempotency key is derived, not generated.** The same shipment
   computes the same key on every machine on every run. A *generated* key is a
   new key on every attempt, which is precisely the thing that books twice —
   and it is the default in most libraries.
2. **It asks the carrier first.** Before booking, it checks whether that
   reference is already present. Local state can be lost — the disk, the
   container, the database restore. The carrier's state cannot.

The acceptance suite kills the run five times at different points and then
checks the **carrier's own books** for a reference booked twice. Checking our
own records would prove nothing; the whole failure mode is the two sides
disagreeing.

---

## 3. What it decides on its own, and what it refuses to

**Decides:** retry or give up; whether an address is usable; whether a result
is worth waiting for; which exception name fits.

**Refuses to decide, always:**

| | Why |
|---|---|
| A UN number | See below |
| What a renamed field means | Only a person can say |
| A postcode that looks wrong | Guessing produces a parcel at the wrong address |
| An image challenge | Not attempted at all |

### Why a UN number is never guessed

A UN number is a legal declaration. The wrong one is not a data error to be
tidied up later — it can ground an aircraft, void the insurance, and put a
fine on the shipper.

**A system that is 95% right about UN numbers commits an offence roughly once
a fortnight.** That is not a good score; it is a compliance problem with a
good score attached.

So there is a table, keyed on the part number. A part that reads as dangerous
and is not in the table **stops the run**. There is no inference step, no
nearest match, no default. `UN3480` (loose lithium cells) and `UN3481` (cells
in equipment) are separate entries and are not interchangeable, because they
are not interchangeable in law.

### Addresses

Validated and tidied before the portal sees them. A four-digit Taiwan postcode
is **refused, not padded** — the three-digit and five-digit forms are both
valid and guessing which one was meant produces a parcel in the wrong
district.

### One-time codes

The run pauses and pushes to the clerk on duty, with a fifteen-minute window.
It does not try to read the code from anywhere. Image challenges are never
attempted, on the grounds that a system defeating a human-presence check is
doing something the carrier has explicitly asked it not to.

---

## 4. The two systems are real, not mocked

`systems/carrier.py` and `systems/legacy.py` are small stateful systems with
their own rules. The bot drives them as it would drive the real ones. Every
behaviour the automation copes with is in there because those systems do it:

**The carrier portal** rejects a weight that does not match its packages,
refuses an aerosol with no declaration and a declaration with a malformed UN
number, rate limits, goes slow, falls over, demands a one-time code, books
**asynchronously** so the tracking number is not in the response, and can ship
a new version that renames two fields.

**The business system** locks a record while somebody has it open, refuses a
write against a revision it has moved past, is **case sensitive on write and
not on read**, and **truncates anything over eighteen characters without
saying so**.

That last one is the nastiest in the set, because it *succeeds*. The write
returns fine; the tracking number in the system is simply wrong from character
nineteen. So the bot reads the value back after every write and treats a
silent truncation as an exception. Nothing else would catch it.

A mock that returns what you expect tests nothing. These return what the real
ones return on a bad morning.

---

## 5. Noticing that the page changed

The script stores a **fingerprint** of the form: the fields, their names,
their order. Each run compares before sending.

The similarity check takes `max(by_words, by_characters)`, because the two
rename shapes defeat different measures — `weight` → `weight_kg` is close by
characters and far by words; `consignee` → `receiver name` is the reverse.
Using either one alone misses half the real cases.

On a mismatch: the run halts **before sending anything**, raises a flag naming
which fields moved, and waits for a developer to acknowledge it. The script is
not rewritten, not adapted, and not retried.

---

## 6. Measured

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

Note what the first row is measured over: **clean** shipments. The nineteen
awkward ones are excluded from it on purpose and counted separately in row
three. A single "98% automated" figure covering both would be the more
flattering number and the less useful one — it would hide whether the
exceptions were handled or merely rare.

---

## 7. What this does not claim

- **It does not claim to be robust against the portal changing.** It claims to
  *detect* that the portal changed and stop. Those are different claims and
  only the second one is keepable.
- **It does not claim driving a screen is a good idea.** It is a last resort,
  for systems with no other way in. If the carrier has an API, use the API —
  this product exists for the ones that do not, and that should be said out
  loud before anybody buys it.
- **It does not self-heal, and will not be made to.** That is a design
  position, not a missing feature. Automatic adaptation is what turns a cheap
  failure into an expensive one.
- **It does not claim 100% will hold on your carrier.** 161 of 161 is against
  a simulated portal built to misbehave in the documented ways. A real portal
  will have failure modes nobody wrote down, and the first month of any
  deployment is discovering them. What transfers is the *structure* —
  checkpoints on the row, a derived key, a fingerprint check, named exceptions
  — not the percentage.
- **It does not defeat human-presence checks.** Image challenges stop the run
  and go to a clerk. A system that got past them would be doing something the
  carrier has explicitly asked it not to do, and that is a commercial
  relationship, not a technical problem.
- **The simulated portal is in-process.** On serverless hosting it resets when
  the function does, and the state screen says so rather than pretending
  otherwise.
