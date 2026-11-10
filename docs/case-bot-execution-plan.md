# Case Bot execution plan

Prepared 10 November 2026. Companion to [case-bot-dashboard-drafting-plan.md](case-bot-dashboard-drafting-plan.md) (the design). This file is the build order: what was checked against the code, what changes in the design, the waves, and the brief for each parallel agent.

## 1. Review of the design against the current branch

Checked on `feat/cases-group-by` at 797b09f. Latest migration is `0050_case_business_entry`.

### Must fix before building

| # | Finding | Resolution |
| --- | --- | --- |
| 1 | The design keeps email outside the assistant's allowlist, but the goal includes sending invoice emails. | New section 2a in the design. The assistant proposes a send as a typed action card. The advocate confirms. The confirm calls the existing `POST /api/appearance-fees/<id>/send/`. The model never sends. Phase E below. |
| 2 | The working tree has about 40 uncommitted files. Worktree agents branch from HEAD and will not see them, and several touch the dashboard and `generate-document-dialog.tsx`. | Commit or stash the Cases/Billing/Messages work first, then cut `feat/case-bot` from the result. Wave 0, your call. |
| 3 | Parallel agents that each run `makemigrations` will all produce `0051`. | Exactly one agent per wave owns models and migrations. Other agents in that wave add no model fields. |
| 4 | `process_jobs` has four lanes (`all`, `interactive`, `search`, `portal`) and a test pins that every job type sits in exactly one of `search`/`portal`. `ProcessingJob.job_type` is `max_length=20`. A `tracking_refresh` type exists that CLAUDE.md does not list. | New type `draft_generation` (16 chars): add to `INTERACTIVE_JOB_TYPES` and to the `portal` lane, priority `PRIORITY_USER`. Update the lane-partition test in the same change. |
| 5 | A practice chat turn is a web request. The pinned worst case for one Case Bot request is 76 s under a 120 s gunicorn limit. | Practice turn budget: at most one classifier call (reuse the single-attempt HyDE timeout) and one synthesis call. Deterministic intents from UI actions skip the classifier. Extend `test_llm_timeouts.py` with the practice path. Draft generation never runs in a request. |
| 6 | `conversations/<id>/export/?format=` is already broken by the DRF format override. | Do not add `?format=` anywhere. DOCX download and any practice export use distinct paths. Out of scope to fix the old one. |
| 7 | Section 5 makes `Case.owner` nullable for firm rows. `OwnedModel.owner` is NOT NULL with PROTECT and every scoped query assumes it. | Firm work does not start until phases A to D ship. Before F2, run a read-only audit of every `owner` filter and write a one-page decision on nullable owner versus a firm-owned service account row. Section 5 below. |

### Simplifications adopted for the first release

These cut scope without changing the safety properties. The design text is unchanged where it is merely more general.

- **One user, so no review state.** Flow is preview, edit, approve, output. "Submit for review" is dropped until firms exist.
- **Approval lives on the revision.** `approved_at`, `approved_by`, `approved_hash` on `AssistantDraftRevision` (immutable otherwise) replace a separate `DraftApproval` table. A separate table returns with firm publishing.
- **Idempotency by natural keys.** `client_request_id` unique per (owner, conversation scope) for chat; unique (draft, version) for revisions; unique (revision, destination) for outputs. No generic idempotency-key table.
- **Two draft subtypes first:** status memo and personal note. The hearing-prep note reuses the facts composed by `core/services/hearing_digest/` and comes after D.
- **Typed practice references as a JSON field** on `Message` (`references`, versioned, validated on write). No new related model.
- **DOCX is rendered synchronously** in the output request (python-docx on a bounded schema is fast). Only generation is a job.
- **Case selection in chat is a chooser, not NLP.** Free text never resolves to a case ID without the server returning candidates.

### Open product decisions (defaults used unless you say otherwise)

1. "Active" case = status not in closed/archived, the same predicate the hearing reminders use.
2. A saved `CaseNote` survives deletion of its draft.
3. Empty source selection means verified case records only, no document retrieval, until a consent line is in the UI.
4. Invoice send from the assistant is one fee per confirmation. No batch send.

## 2. Phases

| Phase | Ships | Flag |
| --- | --- | --- |
| A | Conversation scope, message references, practice read model | none (no user-visible change) |
| B | Overview endpoint, dashboard calendar, practice graph and chat | `PRACTICE_ASSISTANT_ENABLED` (server), `NEXT_PUBLIC_PORTFOLIO_BOT` (client) |
| C | Drafts, revisions, generation job, drafting studio | `CASE_DRAFTING_ENABLED` (server), `NEXT_PUBLIC_CASE_DRAFTING` (client) |
| D | Approval, DOCX export, CaseNote | same as C |
| E | Billing read intent and invoice send card | `PRACTICE_INVOICE_ACTIONS_ENABLED` (server) |
| F1+ | Firms | separate track, section 5 |

Server flags are read with `config(...)` in `settings.py`. Setting them in the production `.env` is an operator step and is flagged, not done.

## 3. Waves and agents

Rules for every wave:

- Each agent runs in its own worktree and owns a disjoint file set, listed in its brief. It touches nothing else and commits nothing unless told.
- One migration owner per wave.
- Contracts are fixed before the wave starts (wave 0 output). Backend and frontend agents build against them, not against each other.
- A wave ends with: merge the branches, full pytest on the throwaway cluster on :55432, `npm install && npm run build && npm run lint && npx tsc --noEmit` in `frontend-next/`, then `api-contract-checker` and, if migrations changed, `migration-reviewer`.
- Tests mock the LLM provider, storage and the mail backend. The local `.env` holds a real Resend key and a production bucket, so no test or agent runs against it unguarded.

### Wave 0. Contracts (main session, serial, short)

1. Branch decision for the dirty tree (finding 2).
2. Write `core/services/practice_assistant/contracts.py` (TypedDicts: `Reference`, `CalendarEntry`, `PortfolioSnapshot`, `PracticeTurn`, `ActionCard`) and the mirror `frontend-next/types/practice.ts`.
3. Write `core/services/drafting/schema.py`: the draft body schema (title, subtype, sections, blocks of paragraph/bullets/table, evidence IDs, verification items, warnings, schema version) with a validator, and the mirror `frontend-next/types/draft.ts`.
4. Add the three server flags to `settings.py`, default off.

Done when both sides type-check against the contract files and nothing else changed.

### Wave 1. Phase A (3 agents)

| Agent | Owns | Work | Done when |
| --- | --- | --- | --- |
| A1 scope (migration owner) | `core/models/conversation.py`, `message.py`, migration 0051, `core/views/chat.py`, `core/views/conversation.py`, their serializers, `test_chat.py`, tenancy tests | `Conversation.scope` (case, legacy_documents, practice), backfill from nullable case, check constraint (case scope has case, others null). `Message.references` JSON. Old chat endpoint rejects a practice conversation with 404. Conversation list excludes practice unless `?scope=practice`. Additive migration, NOT VALID then VALIDATE for the check. | Existing chat and tenancy suites pass unchanged. New tests: backfill of each legacy shape, practice ID rejected on `/api/chat/`, list filter with and without `case_id`. |
| A2 read model | new `core/services/practice_assistant/` (except `contracts.py`), new `core/tests/test_practice_read_model.py` | `portfolio_snapshot`, `calendar_window`, `open_deadlines`, `case_facts`, `resolve_case_candidates`. Owner is a required keyword argument. IST windows through `india_time.py`. Limits 31 days, 25 per page, 100 cap. EXISTS and conditional aggregates, no per-case loops. Returns `as_of`, `timezone`, `total`, `truncated`. | Unit tests for every fixture named in the design checklist (00:30 IST hearing, null due date, dismissed and completed task, cancelled event, exact range end, duplicate titles, two owners). Query count asserted per read. |
| A3 dashboard UI shell | new `frontend-next/components/dashboard/practice/`, new tests | Compact week calendar with day agenda, assistant panel (input, answer, source chips, case chooser, action card slot), all four states. Built on `lib/calendar.ts` semantics against fixture data from `types/practice.ts`. Not mounted yet. | Component tests pass. 320 px reflow and keyboard focus verified. No em dashes in new copy. |

### Wave 2. Phase B (2 agents, then verify)

| Agent | Owns | Work | Done when |
| --- | --- | --- | --- |
| B1 practice API and graph | new `core/views/practice_assistant.py`, new `core/services/graph/practice_graph.py` and `practice_nodes.py`, `core/urls.py`, `test_multi_tenancy.py` reviewed list, new tests | `GET /api/practice-assistant/overview/`, `POST /api/practice-assistant/chat/`. Separate compiled graph: validate scope, pick intent from a closed enum (overview, calendar, open_deadlines, missing_next_date, case_facts), run the typed read, deterministic answer first, optional bounded synthesis, validate cited IDs against the read result. Replay of `client_request_id` returns the stored turn. Server flag returns 404 when off. Existing graph files untouched. | Tenancy tests: user A never sees B through chat, history, sources or filters. Synthesis failure returns the structured result with status `partial`. Timeout budget test passes. |
| B2 wire-up | `frontend-next/lib/api/practice.ts`, hooks, `portfolio-bot-slot.tsx`, `briefing-view.tsx`, `mobile-dashboard.tsx`, Playwright spec | React Query keys with range and auth lifecycle, cache clear on sign-out, mount in the desktop slot and the mobile branch, links from a fixed kind-to-route map, "Ask about this day" fills the input and does not send. | Playwright against mock APIs on desktop and mobile. Build, lint and tsc clean for touched files. |

Verify in the browser with the offline dev server recipe (never the real `.env`), flag on, then screenshot both layouts.

### Wave 3. Phase C (3 agents)

| Agent | Owns | Work | Done when |
| --- | --- | --- | --- |
| C1 draft storage and API (migration owner) | new `core/models/assistant_draft.py`, migration 0052, `processing_job.py` (new type and enqueue helper), `core/admin.py`, new `core/views/case_assistant.py`, serializers, urls, tenancy list | `AssistantDraft`, `AssistantDraftRevision` (with approval fields, unused until D). `POST drafts/` (202), `GET drafts/{id}/`, `POST revisions/` with `expected_revision` (201 or 409), `POST retry/`. Per-owner pending limit. Case, source IDs and origin message validated together under owner. | Foreign case, source, conversation and draft IDs all 404. Stale edit 409. Repeat create with the same request ID returns the same draft. |
| C2 drafting graph and worker | new `core/services/drafting/` (except `schema.py`), new `core/services/graph/draft_graph.py`, `process_jobs.py`, lane test, new tests | Collect facts (read model plus, when sources are selected, the existing owner-and-case scoped retrieval restricted to those document IDs), generate structured JSON, validate against the schema, one bounded repair attempt (pattern from `order_summary/service.py`), reject evidence IDs outside the collected set. Worker commits the preview only if the job claim and expected generation still match. No prompt or body text in logs. | Fake-provider tests: invalid JSON then repair, invented ID rejected, injected instruction inside a document does not change owner, case or destination, late completion does not overwrite a newer revision, wrong-case source fails. |
| C3 drafting studio | new `frontend-next/components/drafting/`, `lib/api/drafts.ts`, entry point on the case page, tests | Brief form (case fixed, type, instructions, audience, tone, sources), job polling, structured preview editor, version history, source inspection, explicit save, unsaved-edits warning, conflict handling. | Component and Playwright tests against mock APIs. Survives reload. |

C2 depends on C1's job type name and model names only. Both are fixed in wave 0 contracts, so they run in parallel.

### Wave 4. Phases D and E (3 agents)

| Agent | Owns | Work | Done when |
| --- | --- | --- | --- |
| D1 approval and outputs (migration owner) | new `core/models/case_note.py`, `draft_output.py`, migration 0053, new `core/services/drafting/approval.py`, `docx_render.py`, output and download views, tests | `approve/` in one transaction: lock draft, check owner, latest revision, evidence still present, store actor, time and hash, 409 when stale. `outputs/` for DOCX (deterministic python-docx, stable storage key, checksum) and note save (unique revision link). Authenticated download on its own path. Case notes list endpoint. | Double approve and double export give one result. Editing after approval cannot release new text. Downloaded bytes and saved note match the approved hash. Storage failure leaves no ready output row. Storage is faked. |
| D2 approval UI | `components/drafting/` approval and export parts, case Notes section | Approve, export, save note, blockers versus warnings, stale and download errors, notes under case detail. | Tests against mock APIs. A real DOCX opened in Word or LibreOffice once by hand. |
| E1 invoice actions | `practice_nodes.py` (billing intent only), `practice_assistant/billing.py`, `components/dashboard/practice/invoice-action-card.tsx`, tests | Read intent `billing_summary` (pending, invoiced and unsent, unpaid, by case). Intent `propose_invoice_send` returns an `ActionCard` built only from server data: fee ID, invoice number, amount, recipient from `get_billing_contact`, blockers (not invoiced, no contact email). The card's confirm button calls the existing invoice and send endpoints. No new send path. | No code path from graph output to `send_invoice`. A test greps for it. Foreign fee ID 404. Missing contact shows a blocker and no send button. With no mail key the result reads "logged", never "sent". Mail backend mocked. |

D1 and E1 touch different files. E1 is the only agent editing `practice_nodes.py` in this wave.

### After each wave

Merge, run the checks, fix, then you review and commit. Enable order in production: migrate, deploy workers, turn on server flag, then client flag.

## 4. Agent brief template

Every agent prompt carries these, because each starts cold:

1. Read `CLAUDE.md`, sections 1 to 4 of the design, and this file's row for the agent.
2. The owned file list. Anything else is read-only.
3. The contract files and that they must not change. A needed change is reported back, not made.
4. Rules: owner scoping on every query and writable FK, no commit or push, no deployment config, no Django upgrade, tests need local Postgres on :55432 and mocked provider, storage and mail, no em dashes in UI copy.
5. The "done when" line, and to report what was not verified.

Model choice: session model for A1, B1, C2, D1 (tenancy, graph, transactions). A cheaper model is enough for A3, B2, C3, D2 with the contracts in hand.

Expected size: 11 implementation agents over 4 waves, plus 2 short review agents per wave. Waves 1 and 2 fit in one day. Stop after wave 2 and use the dashboard before starting drafting.

## 5. Firm track (not started with the above)

Section 5 of the design is a second project, larger than phases A to E together, and its riskiest step changes the tenancy invariant everything else relies on. Order:

1. **F0 audit (one read-only agent, can run during any wave).** List every query, serializer FK, signal, admin class, job and export that filters or stamps `owner`. Output a table: file, line, behaviour if `owner` were null.
2. **F0 decision.** Nullable owner with an exactly-one check, as the design says, or owner stays NOT NULL and firm rows get a `firm` FK plus a policy layer that ignores `owner` for them. Decide from the audit size. Write it into section 5.
3. **F1** (two agents: models and endpoints for firm, membership, invitation, audit; workspace switcher UI). No existing table changes.
4. **F2 onward** one gate at a time, each with the table-driven authorization suite written first.

Firm assistant work (F4) reuses the practice read model by adding a scope argument. That is the reason the read model takes scope as typed input from the start: A2 names the parameter `scope` with one allowed value, `personal`.

## 6. Kickoff prompt for tomorrow

> Read docs/case-bot-execution-plan.md. Do wave 0 yourself, then run wave 1 with three parallel worktree subagents using the briefs in section 3 and the template in section 4. Merge, run the wave checks, and stop for my review.
