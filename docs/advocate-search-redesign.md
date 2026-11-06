# Advocate search redesign

Branch `feat/advocate-search-redesign`. Everything is behind `ADVOCATE_SEARCH_V2`
(default **off**): with it off, the old request shape, the old worker path and the
old page behave exactly as before.

## Status

| Phase | State |
| --- | --- |
| 1. Advocate profile and matching (backend) | built, tested |
| 2. Per-court-complex status and retry | built, tested; "Solve here" **not built** (below) |
| 3. High Court search | report below, then built (backend): our own `showRecords` form, bench runs, endpoints. Tested with the portal faked; **not confirmed against a live search** |
| 4. Frontend | built: two tabs, profile card, per-court status, results, import; 20 browser specs pass |
| 5. India map picker | built and tested, **on by default** (`NEXT_PUBLIC_HC_MAP=false` turns it off); the outline has only had an extent check |

## Decisions and deviations

- **The model is `AdvocateSearchProfile`, not `AdvocateProfile`.** `AdvocateProfile` already
  exists (billing letterhead, one row per user, `/api/advocate-profile/`). The search profile
  is a list, at the plural `/api/advocate-profiles/`.
- **Matching is spaces- and (up to three words) order-insensitive.** "S Kiranmai" and
  "Kiranmai S" are one name, so "Not me" on one removes the other from the name forms, and the
  two lists can never hold either. "Kiranmai" and "Kiran mai" stay two entries because the portal
  searches them differently.
- **A match through a single word is `check`, never `matched`.** That includes a plain listed
  "Kiranmai" and a listed "Kiran mai" against the single-word form "Kiranmai".
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

### What was built after the report

Decision taken: build the High Court advocate search with our own form. Not built: filing-number
search (the portal has it, the library does not; same live check first, and only if wanted).

- `ecourts_parsing.hc_advocate_search_form` and `EcourtsProvider.search_hc_by_advocate`: one
  CAPTCHA-gated request per bench through the library's own CAPTCHA helper, bounded by
  `ADVOCATE_SEARCH_MAX_ATTEMPTS`. `attempts` is the number of form submissions, counted for real.
- `advocate_search_v2`: a High Court search is the same job and the same court rows. The High
  Court is the "district", each chosen bench a row (`complex_code` = the portal's bench code), one
  request per bench (per query for a name search), no session reuse, failures isolated per bench,
  retry of a failed bench by the same endpoint.
- `POST /api/cases/search-advocate/` with `court_type: "high_court"`, `hc_court_code`,
  `bench_codes` (checked against the benches the portal lists, at most 8). Bar number or names.
  A name search answers with a warning: no advocate is named on a High Court row, so every row is
  `check`.
- `GET /api/cases/high-courts/` (the registry, 25 courts, `supported` and why not) and
  `GET /api/cases/high-courts/<code>/benches/` (the portal's benches; the principal seat and the
  registry-named benches start ticked, the rest offered). Calcutta is the one unsupported court.
- A row carries `case_year`; the year range is applied by the page after the fetch, never a new search.
  Pending / Disposed per row is only what was asked: the portal sends no status.
- `manage.py probe_hc_advocate_search --court telangana --bar-code <yours>`: ONE real search with
  a hard cap on HTTP requests; prints the field names of a row, whether any looks like an advocate,
  the case years and the first rows. Writes nothing. **Run this once with a real bar number before
  turning the flag on**: the form's field names come from the portal's own page, but the answer has
  never been read, and the bar-code format (`TS/1234/2009`) is an assumption.

### Open items

1. Run the probe above and share the field names (not the case details).
2. Bombay: all seven portal benches are offered, four ticked (Appellate Side, Aurangabad, Nagpur,
   Goa). Say if the others should go.
3. Filing-number search: only if wanted.

## Phase 4: the page

`/cases/search` asks `GET /api/advocate-search/features/`. With the flag off (or the answer
missing) the page that was there before loads unchanged (`legacy-search.tsx`). With it on, the
redesigned page loads: `?tab=district|hc`, `?job=<id>` (a running or finished search, so a refresh
or a return reopens it; a search left running is picked up on arrival), the result filters, and the
chosen High Court all live in the URL.

- District courts: `AdvocateProfileCard` (bar number, `NameFormChips`, Not me, what goes to
  eCourts and the label preview, all from the server's profile) and `DistrictPicker`. If the
  states or districts do not load, a visible error panel with Retry replaces the list.
- High Courts: `HighCourtPicker` (a keyboard combobox and a tile grid; an unsupported court is
  greyed with the reason) and the form: the portal's benches ticked as above, status, bar number
  or names, a year range that only filters the result.
- Running: `SearchProgress`, `CourtComplexStatus` (failed courts pinned with their reason, Retry,
  "Search only these N again", a link to the court's site) and `LiveMatches`.
- Finished: summary, `ResultFiltersBar` (search, status, court, year, match chips, Show hidden
  with Not me list and Other names, both off), `ResultsTable` (Not me / That's me update at once and
  nothing is searched again) and `ImportBar` (the existing import; courts already in Cases skipped).

Differences from the mock-ups, on purpose or from what the backend can say:

- **No Pause button.** The backend can stop a search, not pause it.
- **No "Solve here"** (see above).
- **District complex counts** show only for ticked districts (each is a portal lookup).
- **Pending / Disposed chips** appear only when rows carry a status. A District Courts grid has
  no status column, so they show for a search asked as Pending or Disposed, not for Both.
- **Filing year** starts at "Any year" so nothing is hidden unasked.

## Phase 5: the India map and the border check

`@svg-maps/india` 2.0.0 (CC BY 4.0, credited under the map and in `NOTICE`), paths untouched.
The jurisdiction table is one file, `frontend-next/lib/hc-jurisdiction.ts`, one line per court.
Tests: every registry High Court is in it (`core/tests/test_hc_jurisdiction.py`, which reads the
file), every one of the map's 36 locations belongs to exactly one court, and the names match
(`__tests__/hc-jurisdiction.test.tsx`, which also drives the map: hover group, click, keyboard,
greyed unsupported court, the small-states column). It differs from the registry in two places:
Ladakh is not drawn separately (one Jammu and Kashmir shape; one court serves both), and the
registry still calls that court "Jammu & Kashmir High Court".

**The map is ON by default** (set `NEXT_PUBLIC_HC_MAP=false` and redeploy to switch it off; the
variable is read at build time). It was switched on on the owner's instruction, with the outline still
only extent-checked, as below.

What the border check found, and did not:

- The package's own metadata and geometry were read. Calibrated on places no one disputes
  (Kanyakumari, Indira Point, Guhar Moti, Kibithu, Delhi), the drawing is a Mercator projection.
  In that projection the Jammu and Kashmir shape reaches **37.10 N**, and runs from **72.60 E to 80.23 E**.
  India's official depiction (all of the former state, Gilgit-Baltistan and Aksai Chin included) reaches
  about 37.1 N and 72.5 E to 80.3 E; the territory India administers reaches about 35.5 N and 73.3 E to
  79.5 E. So the outline follows the **official** extent, not the administered one.
- That is a comparison of extents against published figures, **not** an overlay on the Survey of
  India's own file. Its site offers the political and outline maps and the boundary data only as
  PDF and vector downloads; none was downloaded.
- Not checked at all: every other boundary (Arunachal Pradesh, Uttarakhand's east, the Sir Creek
  edge of Gujarat, the sea limits, the islands).
- Indian law requires published maps to follow the official depiction. **Someone qualified should
  check the outline.** It is on without that check; `NEXT_PUBLIC_HC_MAP=false` brings back the
  combobox and the tile grid.
