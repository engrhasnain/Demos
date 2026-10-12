# How LedgerFlow decides

Every rule, in the order it runs. Nothing here is a model's opinion: each step
is code, each figure has a trace, and the interface will show you both.

---

## 1. Receive

The file is stored with a SHA-256 of its bytes, and the invoice is created at
`received`. **An arrival is a fact.** A document that turns out to be a
duplicate is still recorded, because "we received this twice" is something the
business needs to know. The duplicate is caught at step 4, not hidden at
step 1.

## 2. Read

Header fields and lines come off the page. Two details decide whether this is
useful or infuriating:

**A label only counts at the start of a line.** `Bank account: 581002556171`
sets the bank account. `Should you need to change the bank account: call our
office` does not. The matcher requires the label to begin the line (ignoring
list markers) and to be followed by a separator.

**The first answer wins.** If the invoice number is printed twice, the one in
the header is used, not the one in the footer.

**A hyphen inside a part code is not a minus sign.** `HT-SHC-M8X030-12.9-ZNB`
contains the text `-12.9`. Read as an amount, a four-dollar screw becomes a
credit. The amount pattern refuses to start or end next to a letter, a digit, a
dot or a hyphen.

**A readable barcode outranks the page.** It is machine written and machine
checked. When the square barcode on a Taiwan electronic uniform invoice
decodes, its invoice number, date, net, total and both business numbers are
used, at confidence 1.0, and the timeline says so.

## 3. Check the arithmetic and the identifiers

- Lines add to the net, within one dollar. Suppliers round per line; one dollar
  is not a dispute.
- Business tax is 5% of the net, within one dollar.
- Net plus tax equals the total.
- A uniform invoice number is two letters and eight digits.
- A unified business number passes the weighted checksum. Since April 2023 the
  weighted sum divides by 5 rather than 10, which makes the rule weaker: of the
  72 ways to change one digit of a valid number it rejects 63. That is why a
  valid business number is never treated as proof on its own.

## 4. Is this a repeat?

Five signals, because suppliers resend invoices in five different ways:

| Signal | Catches |
|---|---|
| The same file bytes | The same attachment forwarded again |
| Supplier and normalised number | `INV-0042`, `0042` and `inv 42` are one invoice |
| Supplier, amount and a date window | A re-issue with a new number |
| The number alone | A supplier recorded under two records |
| Order and amount | A statement re-billing a line |

Normalising strips a prefix and leading zeros, so `INV-0042` and `0042` match
while `INV-204417` and `INV-204418` stay different.

A repeat is a **block**. Nothing posts.

## 5. Is it billed to us?

The buyer's business number has to be one of ours, and the invoice has to be
addressed to the legal entity that placed the order. An invoice made out to
somebody else's number cannot be claimed, so it is refused rather than held.

## 6. Has the bank account changed?

If the account on the invoice is not one on file, LedgerFlow:

1. **Blocks the invoice**, and every other open invoice from that supplier.
2. **Raises a call-back** to the telephone number *already on file* — never a
   number printed on the invoice.
3. **Changes nothing.** The supplier record is untouched.

The only way the account changes is a controller recording a confirmed
telephone call, with a note saying who they spoke to. The note is required:
confirming without one is refused. When the call is recorded, the old account
is marked not current, the new one is added as verified, the exceptions are
resolved, the approvals that only existed because of the block are withdrawn,
and the held invoices move on.

This is the control that stops supplier-impersonation fraud, which is the
single most expensive thing that happens to an accounts payable team.

## 7. Three-way match

For each invoice line, paired to an order line by part code, then by wording,
then by substring:

```
delivered to date   = sum of goods receipts against that order line
billed before       = sum of payable quantities on earlier invoices
payable quantity    = min(invoiced, delivered to date − billed before)
```

You pay for what arrived, less what you already paid for. The rest is held,
not refused: the goods may still turn up.

**Price.** A unit price above the order is allowed within the supplier's
tolerance — a percentage or an absolute floor, whichever is larger. Beyond it,
the line is held.

**Charges not on the order.** Freight and handling are accepted up to the
supplier's allowance. Beyond it, held.

**Credit notes are not matched.** There is nothing to match them against. They
are linked to the invoice they credit and the amount is applied.

## 8. Currency

A foreign-currency invoice is converted at the rate for the invoice date, and
both figures are kept. The rate and its source are on the trace.

## 9. Who signs

| Amount in TWD | Who |
|---|---|
| Up to 200,000, nothing wrong | Nobody — it posts |
| Above 200,000 | One signature |
| Above 1,000,000 | Two, and the second from somebody else |
| Anything held | An accountant, before the clean part posts |

A second signature from the same person is refused by the code, not by policy.

## 10. Post

The bill is written against an **idempotency key**: a SHA-256 of the entity,
supplier, normalised number, approved amount and currency.

```
prepare → look for an existing bill with this key
        → found?   use it, record the attempt, do not write again
        → not?     write it, then mark the posting done
```

The dangerous moment is between those two writes: the ledger has the bill and
we do not know it yet. If the connection dies there, the next attempt finds the
bill by its key and attaches to it. **Posting twice is not an error** — a
caller that cannot tell whether its first attempt landed has to be able to ask
again. Refusing the second attempt is how invoices get paid twice.

There is a button in the interface that forces exactly that failure on a real
invoice, so you can watch it.

---

## What stops what

| Severity | Effect | Examples |
|---|---|---|
| **Block** | Nothing posts, nothing is paid | bank details changed, duplicate, wrong business number, wrong entity, arithmetic, barcode disagrees |
| **Hold** | The clean part posts, the rest waits | part delivered, nothing delivered, priced above the order, no purchase order, a field could not be read |
| **Note** | Recorded, stops nothing | the month is closed, arrived very late |
