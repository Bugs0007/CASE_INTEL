# Demo Account Review Checklist

What to click through in the `recruiter` account before sharing access, so it
reads as a working advocate's workspace rather than a half-loaded one.

Run `python manage.py setup_demo_account --verify` first — it prints counts for
most of the items below and flags what's still missing. Use this document for
the parts a count can't tell you (does it *look* right).

---

## 0. Preconditions

- [ ] Password set: `python manage.py changepassword recruiter`
- [ ] Worker is up: `systemctl status case-intel-worker` — **nothing below
      processes without it** (documents sit at "pending" forever)
- [ ] Billing letterhead filled in, or invoices render headed "Advocate" with a
      blank address. Set via `setup_demo_account --letterhead-name ... --address ...`
      or `PATCH /api/advocate-profile/`

---

## 1. Login and first impression

- [ ] Log in at `/login` — lands on `/dashboard`
- [ ] Dashboard is not empty: **Needs Attention**, **Cases by Urgency**,
      **Hearing density strip**, and **Recent Activity** all show real rows
- [ ] `/cases` lists the imported cases with real party names (not CNRs as titles)

> Cases imported from advocate search get `title = case_number` by default.
> If titles look like bare numbers, edit a few via the case-details form so the
> list reads like a real caseload.

## 2. Case detail — the page that carries the demo

Open 2–3 cases from `/cases` and confirm each shows:

- [ ] **Court Tracking card** — CNR, next hearing, last refreshed, and a
      populated **Hearing History** table (expand it)
- [ ] **Case Overview** — parties, court, status
- [ ] **Hearings list** — real dates, judge and purpose per row
- [ ] **Client contacts** — add one with an email on at least one case
      (needed for the invoice step, and an empty contacts block looks unfinished)
- [ ] **Case Bot** panel answers a question about the case
      (needs at least one processed document — see §3)

## 3. Documents and AI

- [ ] `/documents` lists files with status **completed** (not pending/failed)
- [ ] Upload one PDF to a case — it reaches "completed" on its own within a
      minute or two; no manual step needed
- [ ] Ask the Case Bot something answerable from that document and confirm it
      cites the document

## 4. Court orders and summaries

- [ ] At least one case shows an **Order Overview** card with a real AI summary
- [ ] Order PDFs open from the case page

> Order sync runs automatically after a tracking fetch, and summaries generate
> automatically after each order PDF processes. Many genuine cases have **no**
> orders uploaded by the portal at all — if none of your imported cases show
> orders, import a couple more rather than assuming something is broken.

## 5. Cause list (needs a manual run)

Nothing schedules this. To get a cause-list badge to appear:

- [ ] Confirm at least one **High Court** case with tracking enabled and a
      hearing dated today/tomorrow
- [ ] Run it: `python manage.py fetch_cause_lists`
- [ ] Check `/calendar` — the hearing shows a **Listed / Item N / Court hall**
      badge

> **Caveats worth knowing before you demo this.** Only the *Telangana* High
> Court list is fetched, but the matcher pulls in every `high_court` case — so a
> non-Telangana HC case will be checked against the Telangana list and marked
> "not listed", which is a false negative, not a bug you introduced. And a badge
> only appears on days the court actually lists that matter. If nothing lists,
> demo the calendar without leaning on this feature.

## 6. Invoice (API only — no UI buttons)

The frontend shows fee/invoice **state** (badges on hearing rows, the Fee
Summary card) but has no controls to create a fee or generate an invoice. Do it
from the shell, then verify it renders:

```bash
python manage.py shell
```

```python
from django.contrib.auth.models import User
from core.models import AppearanceFee, Hearing
from core.services.invoice_service import generate_invoice, mark_paid

user = User.objects.get(username="recruiter")
hearing = Hearing.objects.filter(owner=user, source="ecourts").order_by("-hearing_date").first()

fee = AppearanceFee.objects.create(owner=user, hearing=hearing, amount="15000")
generate_invoice(fee)        # allocates INV-0001, renders the PDF, -> INVOICED
mark_paid(fee)               # optional: -> PAID, for a second badge state
```

- [ ] Hearing row now shows a fee badge reading **"Invoiced as INV-0001"**
      (or "Paid")
- [ ] Case detail **Fee Summary** card shows non-zero pending/invoiced/paid
- [ ] Download the PDF (`GET /api/appearance-fees/<id>/invoice/file/`) and check
      the letterhead is not blank

> Do at least two fees in different states (one invoiced, one paid) so the
> summary card isn't a single number. Don't call `send_invoice()` unless
> `RESEND_API_KEY` is set and the from-domain is verified — without it the send
> is only logged, and the fee records `send_status='logged'`, never `'sent'`.

## 7. Final sweep

- [ ] `/calendar` — month and by-court views both populated
- [ ] `/emails` — either connected and synced, or accept it will look empty
      (Gmail OAuth is per-account; skip it in the demo if not connected)
- [ ] `setup_demo_account --verify` reports **no stuck or failed background jobs**
- [ ] Log out and back in once — confirms the password works from a clean session

---

## Things that will look empty — decide before you share

| Area | Why | Do |
|---|---|---|
| Travel bookings | API exists, no UI outside the `/walkthrough` mock tour | Don't demo it |
| Fee/invoice buttons | Display-only in the real app | Create via shell (§6), demo the badges |
| Emails | Needs per-account Gmail OAuth | Connect, or skip |
| Cause list | TS HC only, manual run, court must list that day | See §5 |

`/walkthrough` is a scripted tour on **mock data** — it always looks complete
and touches none of this account's real data. Good as an intro, but show the
real `/dashboard` and a real case page too, or the demo proves nothing.
