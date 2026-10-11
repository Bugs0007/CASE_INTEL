# Cause-list expansion - plan (Phase 1 output)

Status: **recon + live spike done; no application code changed.** Only additions in the working tree: `docs/causelists/{COVERAGE,PLAN}.md` and real fixtures under `core/tests/fixtures/causelists/{hcservices_generic,district_ecourts,supreme_court}/` (each directory has a `SOURCE.md`). Nothing committed. `.env` untouched; no DB was touched (the spike used the portals only).

Evidence for every claim below is in `COVERAGE.md` or the fixtures.

---

## As built (Phases 2-5) - where the build departed from this plan

Phase 1 text below is left as written. What changed when the code was written:

1. **Decisions applied** (owner, 2026-10-10): PDF links only for the Supreme Court, everywhere else a "verify on the court's site" link; all dates IST in code, timezone named in the timer; `court_locator` approved (backfill derives from stored data first, then a captcha-free complex lookup, then at most `--limit` throttled CNR lookups); fixtures unscrubbed and trimmed to the pages tests need; one lock per portal plus *no run at all* while an advocate search/import runs.
2. **No separate J&K parser**: the common table parser reads J&K's lists; `PARSER_JK` maps to it. **Delhi is supported** (own parser, 7 real lists of 5 kinds) rather than "partial".
3. **18 of 25 High Courts covered** (Telangana + 17 via hcservices); 7 plus the Madras-Madurai bench resolve to `unsupported`, one test each.
4. **Two extra bugs found and fixed while testing**, both would have produced wrong answers: Telangana filing numbers that wrap to `/(Filing` were indexed as registration numbers; application items (`13) IA NO. 1/2025 ... IN LA.App./20/2026`) were matched on the application's number instead of the case's.
5. **Parser completeness guards went further than planned**: item-number continuity (1..N), case-column coverage, raw link counts (district), pairing ratio. They caught real partial parses during the build (Manipur, Tripura).
6. `parse()` returns a `ParsedDoc` (entries + the document's own date), not a bare list, so a document for the wrong date is refused.
7. `CAUSE_LIST_COURTS` is no longer consulted; the setting is `CAUSE_LIST_ADAPTERS` (a stale `.env` value cannot keep the new adapters off).
8. Old package `core/services/cause_list/` is gone; Telangana's parser lives in `causelists/adapters/telangana_hc.py` unchanged.

Manual EC2 steps (nothing here was changed in deploy files):
- `git pull`; no new Python dependency (PyPDF2/pdfminer/bs4/lxml/httpx/bharat-courts/ddddocr already pinned); `python manage.py migrate` (0043: 5 new columns, 1 nullable JSON column, 2 new tables - no table rewrite).
- `python manage.py backfill_court_locators --dry-run`, then `--limit 25` repeatedly (or just let the next refresh fill them).
- Timers: `systemctl enable --now case-intel-causelist@all.timer`, `systemctl disable --now case-intel-causelist@telangana_hc.timer`; in the timer unit set `OnCalendar=*-*-* 19:00:00 Asia/Kolkata` and `06:30:00 Asia/Kolkata`; consider raising the service's `TimeoutStartSec=1800` only if you raise `CAUSE_LIST_MAX_RUN_MINUTES` (default 25).
- Optional `.env`: `CAUSE_LIST_ADAPTERS`, `CAUSE_LIST_MAX_RUN_MINUTES`, `CAUSE_LIST_LOCK_WAIT_SECONDS`, `CAUSE_LIST_MIN_REQUEST_GAP_SECONDS` (all have defaults).
- Smoke test: `python manage.py fetch_cause_lists --check` then `--dry-run`.

---

## 1. What the spike found (and what it changes)

**1. The false "not listed" bug, root cause.** `registry.py` registers Telangana HC with `hearing_filter={"case__tracking_enabled": True, "case__court_type": "high_court"}`. That matches *every* High Court case, not Telangana's. An Andhra, Bombay or Madras HC hearing is checked against the Telangana list, is absent, and `apply_cause_list` stamps `not_listed`. District cases are never touched (filter excludes them), so they show nothing. Fix = `resolve(case)` decides the court from the case's own data (`tracking_config.hc_court_code`, else `bharat_courts.infer_court_from_cnr`), and a case no adapter claims becomes `unsupported`.

**2. The current code has two more routes to a false `not_listed` / wrong state that the prompt did not mention.**
- (a) *Skipped documents.* `_fetch_cause_list_day` logs a warning and skips any PDF that fails to download/parse ("one unreadable document must not lose the other 57"). A case that sits in a skipped document is then "not in any parsed document" -> `not_listed`. This is not hypothetical: on Sat 20:35 the Telangana meta table listed Monday's rows while the PDFs answered `Order not uploaded`.
- (b) *CAPTCHA failures read as "nothing published".* bharat-courts only retries on the quoted string `"Invalid Captcha"`; the portal's real bodies are `Invalid Captcha` (unquoted) and `{"Error":"ERROR_VAL"}` (empty-CAPTCHA, reproduced). `parse_meta_table` returns `[]` for any short table-less body -> `CauseListNotPublishedError` -> `not_published`.

Both are fixed by the **`not_listed` rule in section 4**: a hearing may only become `not_listed` when *every* document the portal's own index lists for that target was fetched and parsed. Anything less is `not_published` (documents not up yet) or `fetch_failed`.

**3. bharat-courts cannot be trusted for cause lists.** `DistrictCourtClient.cause_list()` reads the wrong JSON key (`causelist_data`; the portal sends `case_data`) and assumes the wrong columns, so it returns `[]` for every court. `HCServicesClient.cause_list()` mis-joins the PDF URL (already worked around) and mis-detects CAPTCHA failure. Plan: **reuse only its transport and CAPTCHA solver** - `HCServicesClient._init_session/_solve_captcha`, our `_TokenSeedingDistrictClient._init_session/_post_ajax` - and write our own request/response handling with an explicit response classifier (`table | none_available | captcha_failed | not_uploaded | other`).

**4. "Config-driven hcservices_generic" is true for fetching, not for parsing.** The fetch flow is identical across all 25 HCs (only `state_code`, `bench_code` differ). The PDFs are not: I read 18 layouts and found four families (F1-F4 in COVERAGE.md) with many per-court variants (`WP 200448/2025`, `1) WP(C)/733/2026`, `1.(1) IA NO.1/2026`, Delhi's wrapped cells). So: one fetch adapter driven by a data table, plus **layout parsers selected per HC**, and an HC only counts as supported when its parser passes golden tests on its real fixtures. I expect F1+F2 to cover about 15 HCs (Andhra, Bombay, Madras-Principal, Karnataka, Calcutta, Patna, Rajasthan, Uttarakhand, Gauhati, Chhattisgarh, Sikkim, Tripura, Manipur, Meghalaya, Orissa) and J&K (F3) to be a second parser. Delhi (F4) may end up `partial`. This is an estimate, not a result.

**5. 7 of 25 HCs are blocked on hcservices** (Allahabad, Gujarat, Himachal, Jharkhand, Kerala: PDFs not served; MP, P&H: "No cause List Available"), plus Madras-Madurai. Those hearings must show **Not covered**, not an empty guess. Native-site adapters (Phase E) are the only route and are out of scope.

**6. District lists are matched on CNR, not case numbers.** Every row carries the CNR in its `viewHistory(...)` handler, so matching is exact and the "per-court case-type alias table" is unnecessary for district courts. Aliases are only needed for HCs.

**7. District granularity is one judge per CAPTCHA request, civil and criminal separately** (5-18 s each). Demand-driven fetching is not an optimisation here, it is the only way the feature is affordable: a 20-hearing advocate spread over ~8 courts is ~8-16 requests, not a state sweep.

**8. District court location is not stored.** The CNR page we already fetch contains the court number+judge, the establishment code (`court_code=2`), state and district codes, but not the court-complex code, and none of it is persisted. A new `Case.court_locator` is needed (section 3); the complex is derived from the district's complex list (est 2 is in `1290019@2,6,11,20`). I verified this end to end on one real case (`TSHC010030082026`: page says court 1, est 2 -> `2^1` -> the CNR is in that court's list).

**9. hcservices PDF links are session-bound** (a cookie-less GET returns `Order not uploaded`). The prompt asks the hearing card to "link to source PDF". For hcservices and district lists that link cannot be the portal URL. Options in section 8 - **needs your decision**.

**10. The schedule is a systemd timer, not cron**, and its timezone is the box's. `settings.TIME_ZONE = "UTC"` and the command uses `timezone.localdate()`. If the box is UTC, "19:00" fires at 00:30 IST and "today+tomorrow" is computed in UTC, so Monday's hearings are first checked early Monday although the lists were up Saturday evening. I cannot see the box; please confirm `timedatectl`. The command will compute dates in `Asia/Kolkata` explicitly (new setting `CAUSE_LIST_TIMEZONE`), independent of the box.

**11. Supreme Court is dormant.** Lists are public, CAPTCHA-free PDFs with a clean index and observable publish times, but an SC case cannot exist in the DB (`Case.court_type` has no SC; `ESCR` CNRs are rejected by the CNR flow). Build parser + tests on the real fixtures; register adapter `supreme_court` as `dormant=True`; no hearing is ever routed to it.

---

## 2. Package layout (`core/services/causelists/`)

```
base.py        CauseListAdapter (abstract), ListingTarget, RawDoc, CauseListEntry, FetchOutcome
registry.py    resolve(case) -> (adapter, ListingTarget) | None ; coverage_for(case) -> Coverage
normalize.py   canonical_case_key(raw, court=None) ; alias tables as data (aliases/*.json)
matcher.py     match(entries, hearings) -> list[Match]  (CNR first, then case key; keeps all hits)
fetchlib.py    response classifier, CAPTCHA budget, polite pacing, streamed PDF download to temp file
lock.py        pg advisory lock + "no portal fan-out job active" check
service.py     run(targets, date) : fetch -> parse -> match -> apply states (the only writer of Hearing.cause_list_*)
adapters/telangana_hc.py       moved from core/services/cause_list/telangana_hc.py (behaviour unchanged)
adapters/district_ecourts.py
adapters/hcservices_generic.py + adapters/layouts/{table_f2,jk_f3,delhi_f4}.py + hc_config.py (data)
adapters/supreme_court.py      (dormant)
```

`core/services/cause_list/` stays as a thin re-export shim for one release so `core.tests.test_cause_list` keeps passing with **import-path changes only** (rule 8). The existing 67 tests in `test_cause_list.py` are the Telangana regression suite.

`CauseListAdapter`:

| member | contract |
|---|---|
| `key`, `display_name`, `dormant` | stable ids; `key` is also the systemd/CLI token |
| `resolve(case) -> ListingTarget \| None` | pure, no network. `target_key` is the sharing unit (e.g. `district:29/2/1290019/2^1/civ`, `hcservices:andhra/1`, `telangana_hc/1`) |
| `fetch(target, date) -> FetchOutcome` | returns the index status plus `list[RawDoc]` (temp-file backed, sha256, source ref, list type, bench label); never raises for portal states, only for bugs |
| `parse(raw_doc) -> list[CauseListEntry]` | pure on a file path; raises `ParseFailure` if a non-empty doc yields 0 entries or fails the count reconciliation below |

**Parse-completeness guard (beyond rule 3).** Each parser also counts item-number-shaped tokens and case-number-shaped tokens straight from the page text, independently of its own column logic, and raises `ParseFailure` when it recovers fewer than 90% of them. A parser that silently drops half a list is the same failure as one that drops all of it, and it would otherwise read as `not_listed` for the dropped half.

---

## 3. Models and migrations

All new migrations are fresh (`makemigrations`), none edits an applied one. Hearing/Case are small tables, but every added column has a default, so no `NOT VALID -> VALIDATE` dance is needed; I'll run the `migration-reviewer` agent on them.

**`Hearing`** (existing fields kept so the API/digest/calendars don't change shape)
- `cause_list_status` choices += `unsupported`, `fetch_failed` (`max_length=20` already fits).
- `cause_list_bench` (Char 255), `cause_list_list_type` (Char 120), `cause_list_note` (Char 200, e.g. `3 of 58 lists not uploaded yet`), `cause_list_source_url` (Char 500, **only stored when the URL works without a session**, i.e. SC). The existing `cause_list_source` keeps holding the adapter/court key.
- These denormalised fields mirror the *primary* match; they are what list views read.

**`CauseListMatch`** (new, `OwnedModel`; owner = hearing owner): `hearing` FK, `fetch` FK (null on delete), `item_number`, `court_hall`, `court_name`, `bench`, `list_type`, `stage`, `matched_by` (`cnr`/`case_key`), `is_primary`, `connected` (JSON, e.g. tagged `wt4`), `created_at`. Unique on `(hearing, fetch, item_number)`. Holds *matched* data only; unmatched entries are never persisted. Registered in `admin.py`; covered by `TestEndpointTenancyCoverage`-style tests if exposed.

**`CauseListFetch`** (new; **not** `OwnedModel` - it holds public court metadata, never user data; I'll say so in the model docstring): `kind` (`index`/`document`), `adapter`, `target_key`, `list_date`, `doc_key`, `list_type`, `bench_label`, `status` (`ok`, `none_available`, `not_uploaded`, `captcha_failed`, `fetch_error`, `parse_failed`, `empty_ok`), `source_ref` (URL; session-bound ones are audit-only), `sha256`, `entry_count`, `doc_total` (index rows only), `error`, `fetched_at`, `attempts`. Unique `(adapter, target_key, list_date, kind, doc_key)` -> re-runs update in place. Same `sha256` + no unresolved hearing => skip the parse (the download still happened, since that is how we hash it).

**`Case.court_locator`** (new JSONField, null): `{"kind": "district", "state_code", "dist_code", "est_code", "complex_code", "court_no", "civil_or_criminal", "resolved_at"}` or `{"kind": "hc", "hc_code", "bench_code"}`. Kept separate from `tracking_config`, which the provider dispatches on and the user-facing setup flow writes. Filled by a small addition to `court_data` parsing (court number/judge, establishment + state/district from the CNR page's own link) and written in `court_tracking._apply_case_data` on every successful refresh - that is the "existing case-refresh flow" the prompt points to. `manage.py backfill_court_locators [--owner U] [--limit N]` does the same for tracked cases that have a hearing in the next 14 days and no locator, one CNR lookup each, capped.

Not touched: any Resend / invoice email path.

---

## 4. State machine - the invariants everything else enforces

| situation (per hearing's target, per run) | state written |
|---|---|
| no adapter claims the case | `unsupported` |
| index says nothing for that date (`No cause List Available`, or index OK with 0 rows) | `not_published` |
| index OK, some documents `not_uploaded`, case not found in the parsed ones | `not_published` (+ note `k of n lists not uploaded`) |
| CAPTCHA budget exhausted / timeout / HTTP error / transport error / `Invalid Captcha` / `ERROR_VAL` | `fetch_failed` |
| any document `parse_failed` and case not found in the others | `fetch_failed` |
| case found | `listed` (+ `CauseListMatch` rows, all hits) |
| **every** document of the index fetched **and** parsed, none contains the case | `not_listed` |
| case has no usable identity (no CNR and no parsable number) | unchanged, logged |

`listed` is never overwritten by any failure state. `not_listed` is reachable only through the single code path in `service.py` that asserts `complete=True`, and `test_causelist_invariants.py` fails if anything else assigns it (grep-style test plus behavioural tests per failure mode).

---

## 5. Demand-driven fetching, safety, budget (t3.small, 2 GB, shared)

- **Targets from hearings**, not from a court list: `Hearing(status=scheduled, date in [D0, D0+2], case.tracking_enabled)` -> `registry.resolve(case)` -> group by `(adapter, target_key, date)`. Users sharing a court share one fetch. A court nobody tracks is never contacted.
- **Order:** adapters run one after another, targets one after another. Concurrency = 1 (HTTP *and* parsing). No threads, no `asyncio.gather` against a portal.
- **Memory:** each PDF is streamed to a `tempfile` and parsed with pdfminer's lazy `extract_pages` page by page; `del` + `gc.collect()` between documents; temp file removed in `finally`. Largest document seen: SC `M_J_1`, 248 pages / 968 KB, 11.6 s on a laptop.
- **Budgets (settings, all env-overridable):** per-request timeout 60 s; CAPTCHA attempts per request 6 (district) / 5 (hcservices); per-adapter wall budget (district 12 min, hcservices 8 min); whole run `--max-minutes` default 25 (the unit has `TimeoutStartSec=1800`); max district courts per run 60; pacing >= 1.5 s between requests to one host (bharat-courts' own 1 s delay stays). Anything cut by a budget leaves its hearings `fetch_failed` with a note, never `not_listed`.
- **Locking.** (1) A Postgres advisory lock (`pg_try_advisory_lock`) so two cause-list runs never overlap. (2) Before any request to `services.ecourts.gov.in`, `ProcessingJob.active_of_type_exists` is checked for `advocate_search`, `advocate_import` and `tracking_refresh`; if any is active, the district adapter skips this run (hearings keep their previous state, logged) and the next timer pass retries. hcservices and sci.gov.in are different hosts from the fan-out jobs, so those adapters are not blocked - say if you want the stricter "never overlaps anything" reading.
- **Evening/morning:** keep the two firings. Evening: `not_published` where lists aren't out. Morning: retry everything that is not `listed`/`not_listed`-final. Dates: IST today..today+2 (the evening run should cover the next sitting day; lists for Monday were up on Saturday evening).

---

## 6. Phases

**Phase 2 - framework + Telangana + states + frontend** (no new courts)
`causelists/` package, models/migrations, registry/normalizer/matcher, response classifier, lock, `service.py` with the section-4 state machine, Telangana moved to `adapters/telangana_hc.py` (same parser, same 67 tests with import changes), `fetch_cause_lists` now iterates adapters (old `--court telangana_hc` keeps working), `causelist_doctor`, serializers (`cause_list_coverage` on Case, new Hearing fields, digest), frontend badges + coverage panel. Regression tests: an Andhra/Bombay HC hearing is `unsupported` not `not_listed`; district hearing `unsupported`; a skipped/`Order not uploaded` document yields `not_published`; a CAPTCHA-failed fetch yields `fetch_failed`; a 0-entry parse of a non-empty document yields `fetch_failed`; `listed` survives each failure. **Telangana's behaviour changes in exactly two intended places** (findings 2a/2b - they were bugs); everything else is byte-for-byte the same, and I'll list both in the report so "Telangana unchanged" stays honest.

**Phase 3 - `district_ecourts`**
Own request layer on `_TokenSeedingDistrictClient` (not `DistrictCourtClient.cause_list`). Locator extraction + `court_locator` + backfill command. Parser: `case_data` table -> entries with CNR, serial, case-type heading, party names; section headings kept as `stage`. Civil/criminal: infer from the case-type token via a small data table; unknown -> request both modes, and `not_listed` only if both succeeded. Golden tests on the 7 saved responses (counts 55 / 86 / 45 / 76 / 75 / 17, empty `Record not found`), the CNR/locator example, and CAPTCHA/`Invalid Request` classification.

**Phase 4 - `hcservices_generic`**
Fetch adapter + `hc_config.py` (state_code, benches with codes and names, flags, parser family, per-HC `status`). Parsers: F2 (adaptive: item column + case column detected per document by evidence, extending the existing cluster approach; handles `1`, `1)`, `1.`, item+case in one block, `1.(1)` sub-items), F1 reuse for Andhra, F3 for J&K, F4 for Delhi only if its golden tests pass. HC `status` in `hc_config` flips to `supported` **only** when its parser passes golden tests (entry count matches an independent token count, plus named known items read off the PDF by eye). Others stay `unsupported` with the real reason (`blocked: PDFs not served`, `no list on hcservices`, `parser not verified`). Multi-bench HCs: bench from `tracking_config.bench_code`/`court_locator`; if unknown, fetch every bench of that HC and accept only an unambiguous hit (several hits are all stored). I have **not** verified that an HC case page exposes its bench - that is the first thing Phase 4 checks; if it doesn't, multi-bench HCs (Bombay, Karnataka, Madras, Allahabad, Calcutta, Gauhati, J&K, Rajasthan, MP) fall back to fetch-all-benches.

**Phase 5 - `supreme_court`**
Index scraper (anchors from `/cause-list/`, never constructed names), parser for `C.A. No. 5981/2023`-style numbers incl. ranges, `Last-Modified` as publish time, public link kept. Dormant, tested on the real fixtures, `causelist_doctor --adapter supreme_court` works. Report states "dormant" explicitly.

---

## 7. Tests

Before: `core/tests/test_cause_list.py` has 67 tests (suite ~680 per CLAUDE.md; I did not run the suite in Phase 1 - it needs the local Postgres recipe). Plan: 67 stay; new suites `test_causelist_framework.py`, `test_causelist_invariants.py`, `test_causelist_district.py`, `test_causelist_hcservices.py`, `test_causelist_sc.py`, frontend badge/coverage tests. Every parser: entry count per fixture document + specific known items. Tests run against local Postgres through shell env overrides only (the repo's `conftest.py` refuses non-local hosts anyway); no live network in tests.

---

## 8. Frontend

States exactly as asked: **Listed** (item, court, bench, list type) / **Not listed** / **Not published yet** / **Couldn't check** / **Not covered for this court**. Case details gets a "Cause-list coverage" line from `cause_list_coverage` (`supported` / `not covered: <reason>` / `unknown until next refresh`), computed server-side from `resolve()` with no network. `CauseListBadge` stays the single shared component (hearing card, both calendars, digest dialog).

**Source link - needs your decision.** hcservices/district PDFs are session-bound, so a stored portal URL shows the user `Order not uploaded`. Options: (a) *link only where public* (SC today) and otherwise show the details with a "Verify on the court's site" link to the portal's cause-list page - zero storage, my recommendation; (b) store the one matched PDF per list in S3 and serve it through an owner-checked endpoint - contradicts "do not persist full unmatched lists" and adds storage; (c) re-fetch on click through a job - 10-60 s and another CAPTCHA per click.

---

## 9. Where the prompt, as written, is wrong or ambiguous

1. "Cron 7pm + 6:30am IST": it is a systemd timer in the box's timezone (finding 10). No unit change is *required* - the instance-templated units stay; the operator enables `case-intel-causelist@all.timer` and disables `@telangana_hc.timer`. `TimeoutStartSec=1800` and an explicit IST `OnCalendar` are deployment-file changes I will not make; I'll list them.
2. "Wrap bharat-courts, don't trust it blindly" - confirmed, and worse than the Telangana PDF-URL bug (findings 3).
3. "hcservices_generic: config-driven adapter for any HC" - fetch yes, parsing no (finding 4).
4. "A parse returning 0 entries from a non-empty document is a failure" - necessary but not sufficient; added the 90% reconciliation guard.
5. "Link to source PDF" - not possible as stated (finding 9).
6. "Telangana behaviour unchanged" - holds except the two real bugs in finding 2, which must change.
7. Rule 5 ("never the production RDS host"): `.env` `DB_HOST` is the prod RDS (see repo memory); every test/command run will pass `DB_HOST=localhost` overrides.

## 10. Decisions I need before Phase 2

1. **Source link:** option (a), (b) or (c) in section 8?
2. **Box timezone:** is the EC2 box on UTC or Asia/Kolkata (`timedatectl`)? Either way I'll compute IST dates in code; this decides whether the evening timer needs `OnCalendar=... Asia/Kolkata`.
3. **`Case.court_locator` + backfill:** OK to add the field and make the case-refresh flow write it (district caching depends on it)?
4. **Fixtures contain real party/advocate names** from public cause lists (the existing Telangana fixtures already do). Fine to commit as-is, or do you want names scrubbed (that would break exact-count golden tests on the text)?
5. **Strictness of the lock:** district adapter yields to advocate/refresh jobs (my default) vs. every adapter yields.

## 11. Manual EC2 steps I expect to list in the final report (preview)

`git pull`; `pip install -r requirements.txt` (no new dependency is planned - pdfminer.six, bs4, lxml, bharat-courts, ddddocr, httpx are already pinned); `manage.py migrate` (3 small migrations); `manage.py backfill_court_locators --limit 200`; timers: enable `case-intel-causelist@all.timer`, disable `@telangana_hc.timer`, raise `TimeoutStartSec` if you want runs over 30 min; confirm `settings.CAUSE_LIST_COURTS` (becomes `CAUSE_LIST_ADAPTERS`, old name still read); optional `manage.py causelist_doctor --adapter district_ecourts --target <key> --date <D>` smoke test.
