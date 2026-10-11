# Cause-list coverage matrix

Live-probed on **Saturday 2026-10-10, 20:30-21:00 IST**, for list dates **Fri 2026-10-09** (past) and **Mon 2026-10-12** (the next sitting day). Every statement below comes from a real response saved under `core/tests/fixtures/causelists/` (each directory has a `SOURCE.md`) or from a probe whose output is quoted. Nothing here was inferred from memory of how the portals "usually" behave. "Untested" means untested.

## Status vocabulary

| status | meaning |
|---|---|
| verified (fetch + fixtures) | A real meta-table and at least one real list PDF were fetched and saved, and the layout was read by eye. **No parser has been run on it yet** - that is Phases 2-4. |
| partial | Fetch works, but the layout (or availability) is hard enough that a parser is not a given. |
| blocked | The portal gives no usable list (no list, or every PDF link says `Order not uploaded`). Not shippable via this source. |
| untested | Not probed. |

## Portal behaviours that change the design

1. **hcservices has three different "no data" responses and only one of them means "no list".**
   - `No cause List Available for this date...!!` - genuinely nothing for that bench/date (MP, P&H, Bombay bench 6).
   - `{"Error":"ERROR_VAL"}` - the request carried an **empty CAPTCHA** (OCR returned `''`). Reproduced: it appears exactly when `captcha == ''`. A CAPTCHA failure, not "not published".
   - `Invalid Captcha` (plain text, no quotes) - wrong CAPTCHA. bharat-courts' `HCServicesClient._post_with_captcha_retry` only looks for the *quoted* string `"Invalid Captcha"`, so it hands this back as a successful response.
   - Roughly 1 in 10 CAPTCHA attempts failed this way during the probe (short or blank OCR decode).
   - The existing Telangana code treats any table-less response under 2000 chars as "nothing published" (`parse_meta_table` returns `[]`), so a CAPTCHA failure currently marks hearings `not_published`.
2. **The meta table can list a PDF that is not served.** The link returns the 21-byte body `Order not uploaded` (HTTP 200, `text/html`). The portal returns the *same* body to a request with no session cookie, so "not uploaded" and "no session" cannot be told apart from outside. Within the session that fetched the meta table, 18 HCs served PDFs normally; 6 (Allahabad, Gujarat, Himachal, Jharkhand, Kerala, Madras-Madurai) served none on any sampled row on either date, so I treat those as not served rather than a session artefact. Telangana's 12 Oct rows were in the same state on Saturday evening while its 9 Oct PDFs were all served.
3. **hcservices PDF links are session-bound.** A cookie-less GET of a link that works in-session returns `Order not uploaded`. The UI cannot send a user to the portal PDF URL (see PLAN.md).
4. **District Courts: one CAPTCHA-gated request returns one court (one judge's list).** There is no complex-wide or establishment-wide list.
5. **bharat-courts 0.3.0 `DistrictCourtClient.cause_list()` is broken.** It reads `causelist_data` / `cause_list_data` from the JSON response, but the portal puts the table under `case_data`, so it returns `[]` for every court. Its HTML parser also assumes columns the portal does not use (it expects `Case Number | Parties | Advocate | Court No | Judge`; the real grid is `Sr No | Cases | Party Name | Advocate Name`). Used as-is it would report every case as absent.

## High Courts via hcservices.ecourts.gov.in (all 25)

Common to every row: **source = hcservices; CAPTCHA = yes** (securimage, solved by ddddocr; a successful meta-table POST took ~2.2 s); **meta format = HTML table** (`Sr No | Bench | Cause List Type | View Causelist`); **list format = PDF**; **granularity = one PDF per judge-combination x list type** (Delhi: one per court number). Only `flag=civ_t` was sent (Telangana's `cri_t` returned nothing; not re-tested elsewhere). **Publish time:** the portal shows no timestamp. Observed: by Sat 20:35 IST the Monday list rows existed for every HC with a 12 Oct entry below.

| High Court | state_code | benches | rows 12 Oct (9 Oct) | list types seen | PDFs served | layout | fixtures | status | notes |
|---|---|---|---|---|---|---|---|---|---|
| Allahabad | 13 | 2: Allahabad, Lucknow | 124 / 146 | Fresh, Additional/Unlisted, Daily IA, Correction Application | **no** | - | meta only | blocked | First 8 rows plus a 6-row spread, both benches, both dates: all `Order not uploaded`. |
| Andhra Pradesh | 2 | 1 | 41 (72) | Fresh Motion, Daily 1/2, Adjourned Motion, Bail, Weekly, Supplementary | yes | F1 (as Telangana) | 12 Oct + 9 Oct | verified | Existing coordinate parser should apply; needs golden tests. |
| Bombay | 1 | 7: Appellate, Original, Aurangabad, Nagpur, Goa, Kolhapur, Special Court (TORTS) | 48 / 38 / 18 / 22 / 4 / 8; bench 6: none | Daily Main, Daily Supplementary, Daily Chamber Main, Officer, Weekly | yes (Appellate; others not downloaded) | F2 | 12 Oct + 9 Oct, bench 1 | verified (bench 1) | Header: `COURT NO. 46`, judges, `AT 11.00 A.M.`. Bench 6 answers "No cause List Available". |
| Calcutta | 16 | 4: Original, Appellate, Jalpaiguri, Port Blair | 55 (Appellate) / 29 / 6 / 1 | Daily List, Warning List, LAWAZIMA, `( Eliminated )` | yes | F2 | 12 Oct, bench 3 | verified (bench 3) | bharat-courts also has a native `CalcuttaHCClient`; not needed. |
| Chhattisgarh | 18 | 1 | 59 | Fresh Matters, List-1 (Top/Sup-1/Sup-2), AR(J) | yes | F2 variant (`1. WA 915/2026`, `1.(1) IA NO.1/2026`) | 12 Oct | verified | |
| Delhi | 26 | 1 | 54 (83) | one type, COMPLETE CAUSE LIST, one PDF per court number | yes | F4 | 12 Oct + 9 Oct | partial | Cells wrap one word per line; case numbers carry typos like `1379//2026`. The PDF links to a native "detailed Causelist". Granularity: court number. |
| Gauhati | 6 | 4: Guwahati, Kohima, Aizawl, Itanagar | 34 / 3 / 6 / 3 | Daily, Supplementary, Hearing, LAWAZIMA | yes (Aizawl) | F2 (`1 WP(C)/150/2026` item and case in one block) | 12 Oct, bench 3 | verified (bench 3) | |
| Gujarat | 17 | 1 | 49 (67) | Daily, Daily Board I, Supplementary Boards, Separately Notified | **no** | - | meta only | blocked | 6 sampled PDFs: `Order not uploaded`. |
| Himachal Pradesh | 5 | 1 | 27 (44) | Daily, Supplementary, Production | **no** | - | meta only | blocked | 6 sampled PDFs: `Order not uploaded`. |
| Jammu & Kashmir and Ladakh | 12 | 2: Jammu, Srinagar | 23 / 8 | Regular, Supplementary-1, Weekly | yes (Jammu) | F3 (`1) WP(C)PIL/17/2020 [CM/4083/2023, ...]`) | 12 Oct, bench 1 | verified | |
| Jharkhand | 7 | 1 | 24 (36) | Daily, Supplementary, Notified Cases | **no** | - | meta only | blocked | 6 sampled PDFs: `Order not uploaded`. |
| Karnataka | 3 | 3: Bengaluru, Dharwad, Kalaburagi | 66 / 19 / 16 (92) | Cause List No. 1-5, Video Conferencing | yes | F2 (`WP 200448/2025`, no slash after the type) | 12 Oct benches 1, 2 + 9 Oct | verified (benches 1, 2) | Header: `COURT HALL NO :1`. |
| Kerala | 4 | 1 | 39 (47) | per-court lists (`1A COURT` ...), Daily List, Mediation | **no** | - | meta only | blocked | 6 sampled PDFs: `Order not uploaded`. |
| Madhya Pradesh | 23 | 3: Jabalpur, Indore, Gwalior | 0 | - | - | - | - | blocked | "No cause List Available" for all 3 benches on both dates. Native only (untested). |
| Madras | 10 | 2: Principal, Madurai | 63 / 26 | Regular, Motion, Additional I-IV, Chambers, Provisional, `( Eliminated )` | yes (Principal); **Madurai no** | F2 (`AND CMP 5478/2022` sub-rows) | 12 Oct, bench 1 | verified (Principal) | Header: `COURT NO. 01` plus sitting time. |
| Manipur | 25 | 1 | 6 | Daily, Supplementary-1 | yes | F2 | 12 Oct | verified | |
| Meghalaya | 21 | 1 | 3 | DAILY | yes | F2 (case and party share a block) | 12 Oct | verified | |
| Orissa | 11 | 1 | 13 | Weekly, Weekly Daily | yes | F2 | 12 Oct | verified | Prints the CNR, `[ ODHC010687532026 ]`, beside each case: an exact match key. |
| Patna | 8 | 1 | (45) | Daily, Production, `( Eliminated )` | yes | F2 | 9 Oct | verified (9 Oct only) | The 12 Oct probe got a blank-CAPTCHA `ERROR_VAL` and was not retried: not conclusive. |
| Punjab & Haryana | 22 | 1 | 0 | - | - | - | - | blocked | "No cause List Available" on both dates. Native only (untested). |
| Rajasthan | 9 | 2: Jaipur, Jodhpur | 50 / 49 | Daily Part A/B, Supplementary Part A/B | yes (Jaipur) | F2 (`URN:` lines) | 12 Oct, bench 1 | verified | |
| Sikkim | 24 | 1 | 1 | Daily | yes | F2 | 12 Oct | verified | |
| Telangana | 29 | 1 | 57 (48) | 8+ types (see existing parser) | 9 Oct yes; **12 Oct: the PDFs tried said `Order not uploaded`** | F1 | 3 Aug (8 types, existing) + 9 Oct | verified (existing adapter) | Rows exist before every PDF is uploaded. Today's code skips such a PDF with a warning, so a case inside it reads `not listed` (PLAN.md, finding 3). |
| Tripura | 20 | 1 | 2 | DAILY MAIN CAUSE LIST | yes | F2 | 12 Oct | verified | |
| Uttarakhand | 15 | 1 | 9 | DAILY CAUSE LIST | yes | F2 | 12 Oct | verified | |

**Totals:** verified 17 (Andhra, Bombay, Calcutta, Chhattisgarh, Gauhati, J&K, Karnataka, Madras, Manipur, Meghalaya, Orissa, Patna, Rajasthan, Sikkim, Telangana, Tripura, Uttarakhand) - partial 1 (Delhi) - blocked 7 (Allahabad, Gujarat, Himachal, Jharkhand, Kerala, MP, P&H). Inside multi-bench HCs only the benches named above were sampled.

### Layout families (18 PDFs read; all text-based, no OCR needed)

- **F1** - Telangana / Andhra: `S.No.`, `Case Number`, `Party`, `Respondent Adv`; IA lines under the case; court hall in the header. The existing parser is built for this.
- **F2** - the common table: item number (`1`, `1)`, `1.`) at the left, case number at a second x-offset. Variants differ in item punctuation, whether the case number shares a text block with the item or the party, and sub-item numbering. Seen in Bombay, Madras, Karnataka, Calcutta, Patna, Rajasthan, Uttarakhand, Gauhati, Manipur, Sikkim, Tripura, Meghalaya, Orissa, Chhattisgarh.
- **F3** - J&K: combined `S.No. & Party Name` column, `1) WP(C)PIL/17/2020 [CM/...]`.
- **F4** - Delhi: narrow wrapped columns.
- Case-number spellings: `WP/29408/2026`, `WP 200448/2025`, `WP(L)/34731/2026`, `L.P.A/100/2025`, `S.A.W. 592/2024`, `WA 915/2026`, `ARB.P.-1379//2026`.

## District Courts via services.ecourts.gov.in

| field | finding |
|---|---|
| source | District Courts portal (`/ecourtindia_v6/`), the same site as case tracking. 36 states/UTs in `bharat_courts.districtcourts.endpoints.DISTRICT_STATES`. **State codes differ from hcservices** (Telangana is 29 on both; Delhi is 7 here and 26 there). |
| CAPTCHA | yes, on every `submitCauseList` (5-18 s per court incl. retries). The `fillDistrict` / `fillcomplex` / `fillCauseList` dropdowns need none. |
| format | JSON envelope; table HTML under `case_data`; columns `Sr No \| Cases \| Party Name \| Advocate Name`. The case cell is `<a onClick="viewHistory('<case_no>','<CNR>',<est>,'','CLcauselist',<state>,<dist>,<complex>,'CauseList')">View</a>` + `CC/100035/2016` + `Next hearing date`. **The 16-character CNR is in every row**, so matching is exact on `Case.cnr_number`; no case-type alias tables are needed. Rows sit under case-type headings (`ORIGINAL SUIT`, `CALENDAR CASE`...). |
| granularity | one **court (judge)** per request: `CL_court_no = "<est_code>^<court_no>"` (e.g. `2^1`), civil (`cicri=civ`) or criminal (`cri`) as separate requests. A court with nothing in that mode answers `Record not found` (101 bytes) - the genuine empty. |
| court dropdown | `cause_list/fillCauseList`, no CAPTCHA. Hyderabad City Civil complex has courts under est 2, 6, 11, 20; Bengaluru City Civil has 81. The label `1-SRI. S SASIDHAR REDDY-CHIEF JUDGE` starts with the same court number the case page shows (`Court Number and Judge: 1-CHIEF JUDGE`). |
| what a tracked case already exposes | The CNR page we already fetch contains `Court Number and Judge`, the establishment name, and a link carrying `state_code=29&dist_code=2&court_code=2` (court_code = establishment code). It does **not** contain the court-complex code; that is found by asking which complex in the district lists establishment 2 (`1290019@2,6,11,20@N`). None of this is persisted today (`_apply_case_data` keeps CNR, party names, advocates). |
| publish time | not exposed. Lists for Mon 12 Oct already existed on Sat 20:38 IST (Hyderabad City Civil 2^1: 45 entries; Bengaluru City Civil 3^1: 17 entries). |
| fixtures | Telangana: Hyderabad City Civil (2^1: 55 and 2^3: 86 entries on 9 Oct; 2^1: 45 on 12 Oct; civil/criminal-mode empty), Hyderabad Criminal (3^1: 76, 3^2: 75 on 9 Oct); Karnataka: Bengaluru City Civil 3^1 (17, 12 Oct); the CNR case page `TSHC010030082026`. The case `OS/336/2026` / `TSHC010030082026` appears in the 2^1 list **and** its case page says court 1, so the locator logic was checked end to end on one real example. |
| status | **verified (fetch + fixtures) for Telangana and Karnataka.** The other 34 states/UTs are untested: same software and endpoints, so expected to behave the same, not claimed. |

## Supreme Court of India

| field | finding |
|---|---|
| source | `www.sci.gov.in/cause-list/` (HTML index) and `api.sci.gov.in/jonew/cl/...pdf` (files) |
| CAPTCHA | **none** for published lists (the AOR/party/court/judge *search* form on the same page is CAPTCHA-gated and not needed) |
| index | The "Published Cause List" tab is an HTML table: rows = dates; columns = Advance, Miscellaneous main/suppl., Regular main/suppl., Weekly; cells are anchors. File names seen: `/jonew/cl/<YYYY-MM-DD>/{M_J_1,M_J_2,M_C_1,M_C_2,M_S_1,M_S_2,M_R_1,F_J_1,M_CC_1}.pdf`, `/jonew/cl/advance/<date>/M_J.pdf`, `/jonew/cl/wk/<from>_<to>/weekly.pdf`. Read names off the index; do not construct them. |
| format | PDF, text-based. `M_J_1` for 12 Oct: 248 pages, 968 KB, 871 numbered items; pdfminer streamed it page by page in 11.6 s on a dev laptop. Case numbers: `C.A. No. 5981/2023`, `SLP(C)`, ranges `8264-8292/2023`. |
| publish time | **observable** via HTTP `Last-Modified`: 12 Oct `M_J_1` Sat 10 Oct 14:23 IST, `M_J_2` 17:57 IST, `M_S_1` Thu 8 Oct, `M_R_1` Fri 9 Oct. |
| public links | **yes** - the PDF URL works with no cookie (verified), unlike hcservices. |
| fixtures | `supreme_court/2026-10-12/` (`index_page.html`, `M_J_1.pdf`, `M_J_2.pdf`) |
| status | **verified (fetch + fixtures); dormant.** A Supreme Court case cannot exist in the DB: `Case.court_type` is `district` / `high_court`, and an `ESCR` CNR is looked up on both portals and rejected as not found. |

## Native High Court sites (Phase E - not built, findings only)

Not probed in this pass. The ones that matter are the courts hcservices cannot serve: **Allahabad, Gujarat, Himachal Pradesh, Jharkhand, Kerala, Madhya Pradesh, Punjab & Haryana, and Madras (Madurai bench)**. Delhi's own PDF links to a native "detailed Causelist". bharat-courts has a native `CalcuttaHCClient`, which is unnecessary because Calcutta's hcservices lists work. Status for every native site: **untested**.

## Outcome after the build (Phases 2-5, 2026-10-10/11)

The matrix above is the Phase 1 probe. After building the parsers and running them over every captured list:

| High Court | final status | what that means |
|---|---|---|
| Telangana | **supported** (own adapter) | the original parser, now also reading the 9 Oct list; filing-number entries that wrap to `/(Filing` are flagged |
| Andhra Pradesh | **supported** | Telangana-family parser; golden tests on 2 lists (49 matters on the 12 Oct pages) |
| Bombay, Calcutta, Chhattisgarh, Gauhati, Karnataka, Madras (Principal), Manipur, Meghalaya, Orissa, Patna, Rajasthan, Sikkim, Tripura, Uttarakhand | **supported** | common item+case table parser; golden tests per list; connected/tagged matters (`with`, `wt7`, `IN <case>`) are read |
| Jammu & Kashmir | **supported** | read by the same table parser (the planned separate F3 parser was unnecessary) |
| Delhi | **supported** | own parser for the hard-wrapped cells; tested on 7 lists of 5 kinds (special benches, division benches, single judges, joint registrars) |
| Allahabad, Gujarat, Himachal Pradesh, Jharkhand, Kerala, Madhya Pradesh, Punjab & Haryana, Madras (Madurai bench) | **not covered** | hcservices serves no usable list; hearings resolve to `unsupported` with the reason (one test per court) |

So **18 of 25 High Courts are covered** (every bench of each, except Madras where only the Principal bench is), 7 are not, and one further bench is not. Supported means a parser passes golden tests on real fixtures - the matter counts are for the trimmed pages in the fixtures, not whole lists. What is *not* verified: the other benches of multi-bench courts (only the benches named in the table above were sampled), lists of kinds not captured (e.g. a Karnataka Dharwad cause list beyond the one sampled), and any list published after 10 Oct. The parsers' completeness guards (item-number continuity, case-column coverage, link counts) exist to turn such surprises into "Couldn't check" instead of a wrong "Not listed".

Two corrections to the probe above, found while building:

- **`flag=civ_t` vs `cri_t`**: re-tested on 16 benches on 10 Oct - the index is identical, so one flag suffices. (Telangana's earlier "`cri_t` returns zero rows" no longer holds.)
- **Patna, 12 Oct**: the probe's `ERROR_VAL` was a blank-CAPTCHA response, not an absent list; a retry returned the index (38 rows).

District Courts: covered in every state in principle (same software); the court location is learned per case from its CNR page at the next refresh (or `manage.py backfill_court_locators`), so a district hearing shows "Covered - starts after the next refresh" until then.
