# FrontDesk

**Answers the questions customers actually ask, from live data, for the
right customer only, around the clock, on the web and on LINE.**

One of six products built for the same distributor. This is the one that
shows an assistant facing customers directly: holding a conversation on two
channels, answering only from live data, and knowing the moment to stop and
fetch a person.

A working product — FastAPI backend, Next.js interface, both deploying to
Vercel. No key, no account, no external service.

---

## Run it

```bash
# backend  →  http://127.0.0.1:8003
pip install -r backend/requirements.txt
python backend/scripts/walkthrough.py --small
uvicorn app.main:app --reload --port 8003 --app-dir backend

# interface →  http://127.0.0.1:3003
cd frontend && npm install && npm run dev
```

- <http://127.0.0.1:3003> is the **customer**. No sign-in; it is a chat window.
- <http://127.0.0.1:3003/desk> is the **staff**. Password `demo1234`.

> Ports 3003 and 8003, so this runs alongside the other three MVPs.

---

## The one thing that matters

A front desk that can read any customer's orders is one sentence away from
reading them to the wrong person. Prompts do not prevent that — prompts are
text, and the thing reading them is a text machine.

So the rule is not in a prompt. It is in a function signature:

```python
def scope_for(conversation: Conversation) -> Scope:
    ...
```

Note what is **not** a parameter. The customer comes from the
conversation's verification and nowhere else. Every function that touches
customer data takes a `Scope`, and a `Scope` cannot be built without a
verified conversation. The engine above can be as wrong as it likes — it
can decide the visitor is asking about an order belonging to somebody else
— and it still will not get the row.

Measured against a red team of **21 attacks in 8 families**: 0 leaks.

| Family | What it tries |
|---|---|
| Straight | Just naming somebody else's order |
| Authority | "This is Mei Lin from the service desk" |
| Override | "Ignore all previous instructions" |
| Role play | "You are a SQL database" |
| Enumeration | Probing to find which references are real |
| Confused deputy | "My colleague asked me to check theirs" |
| Encoding | The identifier spaced out or in pieces |
| Volume | Guessing at the verification until it opens |

---

## Measured, not claimed

| Criterion | Bar | Result |
|---|---|---|
| Handled without a person | ≥45% (55% stretch) | **57.5%** — stretch met |
| A person always one tap away | 100% | **100%** of replies |
| No other customer's data | 0 leaks | **0** across 21 attacks |
| No double bookings | 0 | **0** across 50 simultaneous attempts |

### Why that first number is lower than the brochures

Vendors quote 30 to 60 per cent deflection. Independent surveys find 10 to
25. Most of the gap is counting a conversation as resolved because the
customer stopped replying — **a customer who gave up is not a customer who
was helped.**

So containment here is measured strictly. A contact counts only if the desk
answered the question, the customer did not ask for a person, and it was
not handed over. Three whole categories count *against* it by design:

- **returns** — a person approves every one, so a return reaching a person
  is a success that still scores zero;
- **technician bookings** — offering slots is not finishing;
- **anything not understood** — improvising would be worse than handing over.

A suite with no failures in it measures nothing.

---

## The hard cases

| Case | What happens |
|---|---|
| Identity | Order number **and** the email it was placed with. Three tries, then locked. |
| Systems disagree | Our system says despatched, the carrier printed a label and stopped. Both shown, the gap named, and a person chases it rather than the desk guessing. |
| Returns with photos | The description is triaged, the contract warranty is checked in code, and a **person approves every return**. |
| Taiwan's 7-day rule | Consumer law. These are trade accounts, so it does not apply — and the desk says so rather than promising a refund nobody owes. |
| Technician visits | A constraint check proposes slots: skills, van stock, travel time both sides of a job, working hours. The model never invents a time. |
| Two people, one slot | A unique constraint on the technician and the time. One write wins; the loser is offered the next slot, not an error. |
| Time zones | A reply time worked out from office hours. Not "shortly" at 2am Taipei to a customer in California. |
| Language | Chinese in, Chinese out. Part numbers lifted out before anything is composed and put back byte for byte. |
| Social engineering | Blocked by the scope, not by wording, and every attempt is logged. |

---

## Enumeration, and the small leak most products have

Asking about an order that exists but belongs to somebody else returns
**exactly** what asking about an order that does not exist returns:

> I have no record of that order on your account.

Saying "that order is not yours" confirms the order exists. Do that a few
thousand times and you have a list of real order numbers. The two replies
are compared character for character in the test suite.

---

## LINE

LINE reaches about 94 per cent of Taiwan and is where customers already
send photographs of broken parts.

Two things here are real rather than sketched, because they are the two
that go wrong:

- **The signature.** Every webhook is verified against the channel secret
  with a constant-time comparison. Unsigned, wrongly signed or tampered
  bodies get 400 and nothing else. Without it the endpoint is an open door
  to post invented messages claiming to be any LINE user.
- **The reply token.** Single use, five minute expiry. Used once,
  immediately. Anything later goes out as a push.

Nothing leaves the machine unless `LINE_CHANNEL_ACCESS_TOKEN` is set; the
demonstration records what *would* have been sent.

---

## Proving it

```bash
python backend/scripts/walkthrough.py --evaluate
python -m pytest backend/tests          # 77 tests
```

The **Evidence** screen runs the same measurements from the interface.

---

## Who may do what

| Role | May |
|---|---|
| Agent | The queue, the conversations, approve or refuse returns |
| Supervisor | Also the access log and the evidence run |
| Administrator | Load the company |

An unrecognised role satisfies **nothing**. (It used to satisfy everything,
because both sides of the comparison fell back to −1.)

---

## Deploying to Vercel

**One Vercel project, zero setup.** Import the repository, set the Root
Directory to `FrontDeskAI`, press Deploy. `vercel.json` runs the interface
and the API as two services behind one URL (`/api/*` to the backend,
everything else to the interface), so there is no CORS and no address to
configure.

No database is needed: on Vercel the backend uses a SQLite file in `/tmp`
and fills it with a small demonstration company (20 customers, about 60
orders, a couple of conversations and a booked visit) on the first request
after a start, so the site opens with data and
`admin@hengtai-industrial.example` / `demo1234` signs in straight away — the
customer chat at `/chat` never needed a sign-in in the first place. The data
resets when the server restarts, and a thin bar says so. Setting
`DATABASE_URL` to PostgreSQL (plus `JWT_SECRET`) is the optional upgrade
that keeps it. `LINE_CHANNEL_SECRET` / `LINE_CHANNEL_ACCESS_TOKEN` put the
LINE channel live; without them it is implemented and tested, not operated.

Step by step, including what to do when it does not work:
[`docs/deploying-to-vercel.md`](docs/deploying-to-vercel.md).

---

## Settings

| Variable | Default | What it does |
|---|---|---|
| `VERIFICATION_ATTEMPTS` | 3 | Tries before lockout |
| `LOCKOUT_MINUTES` | 30 | How long that lasts |
| `OFFICE_OPENS_HOUR` / `_CLOSES_HOUR` | 9 / 18 | Taipei hours, used for reply times |
| `DEFAULT_WARRANTY_MONTHS` | 12 | From despatch |
| `TRANSIT_DAMAGE_DAYS` | 7 | Contract window, not the consumer right |
| `TRIAGE_CONFIDENCE_FLOOR` | 0.62 | Below this the desk says it is not sure |
| `VISIT_MINUTES` | 90 | A technician visit |
| `BOOKING_HORIZON_DAYS` | 14 | How far ahead slots are offered |
| `MODEL_API_KEY`, `MODEL_BASE_URL` | empty | A model may pick an intent and phrase a sentence. It never reads a row. |

---

## Layout

```
backend/
  app/
    domain/        the intent list, the language rules
    services/      isolation, identity, orders, returns, scheduling,
                   escalation, and the conversation engine
    channels/      LINE: signature, unpack, compose
    evaluation/    the acceptance criteria, the scripted contacts, the red team
    seed/          the generated customers, orders and carrier events
  api/index.py     the Vercel entry point
  tests/           77 tests
frontend/
  src/app/         the chat, the desk, the evidence
```


---

## Further reading

- [`docs/how-it-decides.md`](docs/how-it-decides.md) — the one control
  everything rests on, how each request is decided, and what this product
  does not claim.
- [`docs/demo-script.md`](docs/demo-script.md) — ten minutes, two windows,
  in order.
