# Advocate search redesign

Branch `feat/advocate-search-redesign`. Everything is behind `ADVOCATE_SEARCH_V2`
(default **off**): with it off, the old request shape, the old worker path and the
old page behave exactly as before.

## Status

| Phase | State |
| --- | --- |
| 1. Advocate profile and matching (backend) | built, tested |
| 2. Per-court-complex status and retry | built, tested; "Solve here" **not built** (below) |
| 3. High Court search | verification report written (below); **nothing built, waiting for a decision** |
| 4. Frontend | not started |
| 5. India map picker | not started |

## Decisions and deviations

- **The model is `AdvocateSearchProfile`, not `AdvocateProfile`.** `AdvocateProfile` already
  exists (billing letterhead, one row per user, `/api/advocate-profile/`). The search profile
  is a list, at the plural `/api/advocate-profiles/`.
- **Matching is spaces- and (up to three words) order-insensitive.** "S Rambabu" and
  "Rambabu S" are one name, so "Not me" on one removes the other from the name forms, and the
  two lists can never hold either. "Rambabu" and "Ram babu" stay two entries because the portal
  searches them differently.
- **A match through a single word is `check`, never `matched`.** That includes a plain listed
  "Rambabu" and a listed "Ram babu" against the single-word form "Rambabu".
- **A grid with no Advocate column is `check`** (nothing to verify against), as before.
- **Rows are classified when read** (`core/services/advocate_results.py`), best match first,
  with counts over all rows. The status endpoint takes the job's profile, or `?profile_id=`.
- **Queries come from one function** (`name_matching.minimize_queries`), read by the profile
  serializer (the card's "What goes to eCourts" box) and by the search start. More than three
  queries returns a warning on the profile.
- **The v2 worker is its own module** (`advocate_search_v2.py`), so the old fan-out is untouched.
  One portal request at a time, the provider's bounded attempts, a bounded whole-district re-read
  for an "every court refused" district, and a court whose first query fails is not tried with
  its second.
- **Retry is a child job** that searches only the chosen courts and merges into the parent's
  results and court rows (`POST /api/cases/search-advocate/<job>/retry/`). The one-search-at-a-time
  cap applies to it.
- **First district-list call**: a dropped connection is retried at 0.5 s, 1.5 s and 3 s (four
  attempts in all) for every court-structure call; a portal that answers with an error is not
  retried. A failure is not cached, so the page's Retry really retries.

## "Solve here" (in-app CAPTCHA): not built

`bharat_courts.captcha.manual.ManualCaptchaSolver(callback)` exists, so the *solving step* is
pluggable. The design asked for (the server fetches the CAPTCHA, holds the portal session between
two requests, then submits) does not fit this deployment:

1. It would put a portal request in the web process while the worker is searching, breaking
   "one portal request at a time, system-wide" (the rule that came out of a production outage).
2. The portal session is an async client on its own event loop; it cannot be shared between
   gunicorn processes (the cache is per-process).
3. The submit path cannot be checked without spending live portal requests.

A variant where the worker waits for a typed CAPTCHA would block the only worker for minutes. So
there is no flag and no button: a failed court shows the courts' own site as a link
(`court_site_url` in `GET .../courts/`).

## Phase 3: High Court verification report

Run on 6 Nov 2026, read-only, **9 requests** (budget 10), 4 s apart: the portal's landing page
(5 fetches, because the library re-initialises its session per call, plus one saved copy that the
forms were read from offline), and `fillHCBench` for three courts. No search was made, no CAPTCHA
read, no name or bar code sent.

**The installed `bharat-courts` has no High Court advocate search.** `HCServicesClient` has
`case_status` (case type + number + year), `case_status_by_party` (party name, year mandatory),
`cause_list`, `court_orders`, `list_benches`, `list_case_types`. There is no `advocate_search`, no
bar-code search and no filing-number search; `hcservices.endpoints` has form builders for exactly
those six. `CalcuttaHCClient` has only `search_orders` (case type + number + year).

**The portal does offer them.** Its own page has Advocate Name, Bar Code and Date Case List
(`radAdvt` = 1, 2, 3) and a Filing Number form (`filing_case_type`, `filing_no`, `filyear`), all
posted to the same `cases_qry/index_qry.php?action_code=showRecords` the library already uses:

- advocate name: `advocate_name`, `search_type=1`
- bar code: `adv_bar_state` (one field, `maxlength 16`, placeholder "barcode"), `search_type=2`
- both: `f` = Pending / Disposed / Both, the bench as `court_code`, `state_code`, `captcha`
- **no year field**, which agrees with "the portal returns the whole book in one call"

So a High Court advocate search can be built the way the District one was (our own form builder
on the client's CAPTCHA helper). Not done: it needs a live CAPTCHA-gated check first.

**Fields on a result row** (the library documents `showRecords` as verified live for party search):
`case_no`, `case_year`, `type_name`, `pet_name`, `res_name`, `lpet_name`, `lres_name`, `cino` (the
CNR), `orderurlpath`, `party_name1/2`. So: case number, **year present on every row**, parties,
CNR. **Not returned**: status, registration date, filing number, bench, and no advocate column is
documented. Consequences, all **unverified for the advocate search** until one real response is read:

- Year filter: works from `case_year`.
- Pending / Disposed per row: not available; only what was asked (`f`). "Both" cannot say which.
- Name search cannot be classified (no listed advocate name), so every row would be `check`.
  A **bar-code search** is the dependable path (the portal matched the bar code itself).

**Bench codes** (live `fillHCBench`, a CAPTCHA-free call the app already caches):

| Court | Codes |
| --- | --- |
| Bombay | 1 Appellate Side, 2 Original Side, 3 Aurangabad, 4 Nagpur, 5 Goa, 6 Special Court (TORTS), 7 Kolhapur |
| Allahabad | 1 Allahabad, 2 Lucknow |
| Telangana | 1 Principal Bench at Hyderabad |

The library registry has 29 entries for 25 High Courts, but it carries bench *names* only
(`bombay-nagpur`, ...), never codes; codes come from `list_benches`. The portal has more Bombay
"benches" than the four in the design (two Mumbai sides, a Kolhapur bench, a TORTS court).

**Calcutta** is a separate client with order search only: no advocate search through this
library. Whether `hcservices` serves Calcutta at all was not probed. Mark it unsupported.

### Decisions needed

1. Build the High Court advocate search with our own `showRecords` form (bar code first)?
   It needs one live CAPTCHA-gated bar-code search, with a real bar number, to read the real
   row shape and the exact bar-code format before anything ships.
2. Which Bombay benches to offer (4 as designed, or all 7)?
3. Filing-number search: the portal has it, the library does not. Build only after the same
   live check, and only if you want it.
