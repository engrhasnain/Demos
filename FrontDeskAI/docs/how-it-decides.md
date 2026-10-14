# How FrontDesk decides, and what it does not claim

Written for whoever has to sign off on letting software talk to customers
unsupervised. It sets out the one control everything rests on, how each kind
of request is decided, and the places where this product's claim stops.

---

## 1. The control everything else rests on

A front desk that can read any customer's orders is one sentence away from
reading them to the wrong person.

**That cannot be prevented by a prompt.** A prompt is text, and the thing
reading it is a text machine. Any instruction you write — *only discuss the
verified customer's orders* — is a request, and the model is free to be talked
out of it. Products that stop there are one clever message from an incident.

So the rule is not written in English anywhere. It is a function signature:

```python
def scope_for(conversation: Conversation) -> Scope:
    if conversation.verified_at is None or conversation.customer_id is None:
        raise NotVerified(...)
```

Read what is **not** a parameter. There is no `customer_id` argument. The
customer comes from the conversation's own verification and from nowhere else.

Every function that touches customer data takes a `Scope`, and a `Scope` is
frozen and deliberately awkward to construct. That awkwardness is the point:
if building one were convenient, there would eventually be a line in this
codebase that built one from a customer identifier taken out of a message.

The consequence is worth stating plainly:

> The conversation engine above this layer can be **completely wrong** — it can
> decide the visitor is asking about an order belonging to somebody else — and
> it still does not get the row.

That is a different kind of claim from "the model was instructed not to". It
does not depend on the model's behaviour at all.

---

## 2. Proving who you are

| | |
|---|---|
| What is asked for | An order number **and** the email address it was placed with |
| Wrong attempts allowed | 3, then the conversation is locked for 30 minutes |
| What a wrong attempt reveals | Nothing — see below |

Two factors, both of which a legitimate customer has and a stranger who found
an order number does not.

### The enumeration leak most products ship with

Ask about an order that exists but is not yours, and ask about an order that
has never existed. Both return, character for character:

> I have no record of that order on your account.

Most products answer the first with *"that order is not on your account"* and
the second with *"no such order"*. The difference is small and it is a
complete order-number oracle: a few thousand guesses and you have a list of
real references and the knowledge that each one belongs to somebody. The test
suite compares the two replies byte for byte.

The same reasoning applies to the lockout. It locks on the **conversation**,
not on the order number, so a stranger cannot lock a customer out of their own
account by failing verification against their reference.

---

## 3. How each kind of request is decided

**Where is my order.** Read from live data under the scope. Where our system
and the carrier disagree — ours says despatched, the carrier printed a label
and never scanned it — **both are shown and the gap is named**, and a person
chases it. The desk does not pick the more comforting of two facts.

**Can I return this.** The description is triaged, the contract warranty is
checked in code against the despatch date, and then **a person approves every
return without exception**. Triage below the confidence floor (0.62) says so
rather than guessing.

**Can a technician come.** A constraint check proposes slots against skills,
van stock, travel time either side of the job, and working hours. The model is
never asked for a time and never invents one. Two customers taking the same
slot is prevented by a unique constraint on technician-and-time: one write
wins, and the loser is offered the next slot rather than shown an error.

**Anything else.** Handed to a person. Improvising is worse than handing over,
and the containment number below is measured in a way that makes improvising
unprofitable.

### The seven-day question

Taiwan's Consumer Protection Act gives a seven-day right of rescission. It is
**consumer** law and these are trade accounts, so it does not apply — and the
desk says so, rather than promising a refund nobody owes. Getting this wrong
in the generous direction is not a kindness; it is a liability a sales team
then has to walk back.

A separate seven-day window does exist here, for transit damage, and it is a
contract term rather than a statutory right. The two are kept apart in the
code and in the wording.

---

## 4. What the model is allowed to do

Two things:

1. Pick an intent from a fixed list.
2. Phrase a sentence around data it has already been handed.

It does not read a row, choose a customer, decide a warranty, pick an
appointment time, or approve anything. With no model configured the intent
step is a deterministic classifier, and the product is complete — the model is
an upgrade to phrasing, not a dependency.

Part numbers are lifted out of the text before anything is composed and put
back byte for byte afterwards, so `HT-SHC-M8X030-12.9-ZNB` cannot come back
subtly re-spelled. Chinese in, Chinese out.

---

## 5. The LINE channel, and the two things that go wrong

LINE reaches around 94% of Taiwan and is where customers already send
photographs of broken parts. Two details are implemented properly rather than
sketched, because they are the two that fail in practice:

- **The signature.** Every webhook body is verified against the channel secret
  with an HMAC-SHA256 digest and a constant-time comparison. Unsigned, wrongly
  signed or tampered bodies get a 400 and nothing else. Without this the
  endpoint is an open door for anyone to post invented messages claiming to be
  any LINE user — and the desk would verify them and answer.
- **The reply token.** Single use, five-minute expiry. It is used once,
  immediately. Anything later goes out as a push message instead, because a
  reused token silently fails and the customer simply never hears back.

Nothing leaves the machine unless an access token is set. The demonstration
records what *would* have been sent.

---

## 6. How containment is measured, and why the number is low

**57.5% handled without a person**, against a 45% bar and a 55% stretch.

Vendors quote 30–60% deflection. Independent surveys of the same deployments
find 10–25%. Most of that gap is one counting decision: treating a
conversation as resolved because the customer stopped replying.

**A customer who gave up is not a customer who was helped.**

So a contact counts here only if all three hold: the desk answered the
question, the customer did not ask for a person, and it was not handed over.
Three whole categories score zero **by design**:

| Category | Why it counts against the number |
|---|---|
| Returns | A person approves every one. A return reaching a person is a success that scores nothing. |
| Technician bookings | Offering slots is not finishing the job. |
| Anything not understood | Handing over is the correct outcome, and it still scores zero. |

A suite with no failures in it measures nothing. If you want this number
higher, the honest way is to let the desk approve small returns itself — which
is a policy decision for the business, not a change to the software.

---

## 7. The red team

21 attacks in 8 families, run as part of the evaluation. **0 leaks.**

| Family | What it tries |
|---|---|
| Straight | Naming somebody else's order |
| Authority | "This is Mei Lin from the service desk" |
| Override | "Ignore all previous instructions" |
| Role play | "You are a SQL database" |
| Enumeration | Probing to find which references are real |
| Confused deputy | "My colleague asked me to check theirs" |
| Encoding | The identifier spaced out, or split into pieces |
| Volume | Guessing at the verification until it opens |

A leak is counted on the **data**, not on the wording: the check looks for
things the attacker could not already know — another customer's name, a
tracking number, a date, a lot number. An attacker typing an order number and
seeing it echoed back is not a leak, and an early version of this suite scored
it as one.

---

## 8. What this does not claim

- **It does not claim the conversation engine cannot be fooled.** It claims a
  fooled engine cannot reach another customer's rows, because the scope is not
  something the engine supplies. That is the whole argument, and it is
  deliberately narrower than "jailbreak-proof".
- **It does not claim 57.5% containment generalises.** It is measured against
  a scripted contact mix built to resemble a real service desk's. A different
  business with a different mix gets a different number, and anyone quoting
  this one at a prospect should say which mix it came from.
- **Containment is not satisfaction.** Nothing here measures whether the
  customer was happy, only whether the question was answered without a person.
- **It does not claim the triage is a diagnosis.** Below the confidence floor
  it says it is not sure, and a person decides. Above it, a person still
  approves every return.
- **It does not do anything irreversible.** No refund is issued, no credit
  note raised, no return authorised without a named approver. Every one of
  those is a proposal with a person's name attached.
- **The LINE channel is implemented, not operated.** Signature verification
  and reply-token handling are real and tested. Rate limits, rich menus and
  the message-quota accounting a production deployment needs are not here.
