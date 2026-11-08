# Case Intel Case Bot implementation handoff

Prepared 8 November 2026. This is an implementation plan for the current Django and Next.js application. Proposed routes, limits, models, and rollout gates are design decisions for the implementation agent to validate against the current branch.

## Product outcome

1. **Dashboard assistant.** Add **Ask about your practice** and an interactive calendar to the dashboard on desktop and mobile. The assistant answers across the signed-in advocate's cases with exact counts, explicit date ranges, and links to the case, hearing, deadline, or appointment behind each answer.
2. **Case drafting.** From an individual case, or after explicitly choosing one from the dashboard, generate a case status memo, a hearing-prep note, or a free-form personal note. Use the advocate's brief, selected material, and verified case records. Offer an editable preview, version history, and source inspection.
3. **Approved output.** Export an approved memo as DOCX or save an approved note to the selected case. Filing, email, calendar mutation, and changes to case facts stay outside the assistant's action allowlist.

The dashboard calendar starts as a compact selectable week with a day agenda and an **Open full calendar** link. The case overview shows exact portfolio totals and a short, paginated list with status, court, and next hearing, plus a link to the full Cases page. Extend the full calendar for any additional views through its existing route. Open the [review console](case-bot-review-console.html) locally to explore these interactions with fixed sample records.

## Repository map

| Area | Current entry point | Implementation implication |
| --- | --- | --- |
| Dashboard shell | [dashboard/page.tsx](../frontend-next/app/(dashboard)/dashboard/page.tsx), [briefing-view.tsx](../frontend-next/components/dashboard/briefing-view.tsx), [mobile-dashboard.tsx](../frontend-next/components/dashboard/mobile-dashboard.tsx) | The dashboard has distinct desktop and mobile branches. Put the assistant and compact calendar in both through shared components and state. Preserve existing briefing, map, billing, and needs-attention behavior. |
| Bot mount point | [portfolio-bot-slot.tsx](../frontend-next/components/dashboard/portfolio-bot-slot.tsx), [feature-flags.ts](../frontend-next/lib/feature-flags.ts) | Fill the reserved slot. The existing client flag controls visibility. Add a separate server-side rollout check on the new endpoints. |
| Current calendar | [calendar/page.tsx](../frontend-next/app/(dashboard)/calendar/page.tsx), [lib/calendar.ts](../frontend-next/lib/calendar.ts), [india_time.py](../core/services/india_time.py) | Calendar combines Hearing, Task, and CaseEvent. Preserve India day keys, kind order, and status handling when building the dashboard version. |
| Chat and history | [chat.py](../core/views/chat.py), [conversation.py](../core/views/conversation.py), [conversation model](../core/models/conversation.py), [chat-panel.tsx](../frontend-next/components/chat/chat-panel.tsx), [chat API client](../frontend-next/lib/api/chat.ts) | The existing nullable case ID means a legacy document conversation when no case is set. It does not identify a dashboard assistant conversation. Distinguish these scopes explicitly. |
| Graph and evidence | [builder.py](../core/services/graph/builder.py), [nodes.py](../core/services/graph/nodes.py), [state.py](../core/services/graph/state.py), [ai_workflow.py](../core/services/ai_workflow.py), [citation.py](../core/models/citation.py) | The current graph compiles without a checkpointer and runs HyDE, owner-scoped hybrid search, then answer generation. Django persists conversations, messages, and citations. Preserve this path for existing chat. |
| Document and note surfaces | [case model](../core/models/case.py), [template API](../core/views/doc_template.py), [template engine](../core/services/doc_templates/engine.py), [document views](../core/views/document.py), [generate-document-dialog.tsx](../frontend-next/components/documents/generate-document-dialog.tsx) | The case has a single notes field. The existing generation endpoint merges deterministic forms. Add independently editable notes and AI drafts alongside those surfaces. Reuse document storage, renderer utilities where appropriate, and authenticated file retrieval. |
| Jobs and AI providers | [processing_job.py](../core/models/processing_job.py), [process_jobs.py](../core/management/commands/process_jobs.py), [case briefing](../core/services/hearing_digest/briefing.py), [ai_service_factory.py](../core/services/ai_service_factory.py), [requirements.txt](../requirements.txt) | Use the existing PostgreSQL queue and configured provider. Current dependencies pin LangGraph 0.6.11 and include python-docx. Order Overview is a separate single-order pipeline. |
| Security and verification | [CLAUDE.md](../CLAUDE.md), [test_multi_tenancy.py](../core/tests/test_multi_tenancy.py), [test_chat.py](../core/tests/test_chat.py), [conftest.py](../conftest.py) | New data rows are owner-scoped. Extend the tenancy route audit. Use a local PostgreSQL with pgvector for DB tests and mock provider/storage calls. |

## 1. Scope and shared reads

### Conversation scope

- Add a persisted discriminator to Conversation with three values: **case**, **legacy_documents**, and **practice**. Backfill existing rows in a new migration from nullable case ID, with positive fixture coverage for each legacy shape. Preserve primary keys, messages, citations, titles, and exports. Constrain case scope to a case FK and practice/legacy document scope to a null case FK.
- Keep the existing /api/chat/ contract and behavior for legacy callers. Reject a practice conversation ID on the old chat endpoint. Add /api/practice-assistant/chat/ for practice turns. The endpoint sets practice scope itself and obtains owner identity from request.user. Continue a practice conversation only when both owner and scope match. Use a consistent 404 for an inaccessible resource.
- Filter existing conversation listing by its old scope behavior, excluding practice unless a new explicit scope filter is present. Verify the case-panel request with and without case_id and the original all-document listing. Shared detail, messages, export, and deletion may serve practice history after owner validation if their representations support practice references.
- Starting a draft from a practice response creates a new case-scoped draft with a verified case ID and an optional trace link to the practice conversation. A draft never inherits the entire practice chat as context. The server validates the case, source IDs, and optional originating message together. Apply the same case restriction for source selection from a case conversation.

### Practice read model

Implement a reusable owner-scoped service under core/services/practice_assistant/ (proposed). Have both the calendar endpoint and graph nodes call it directly. It accepts typed arguments for date range, kinds, case filters, and pagination. All filtering, counting, ordering, and date arithmetic occur in code or SQL.

| Read | Return and source | Rules |
| --- | --- | --- |
| Portfolio snapshot | Counts by Case.status, active cases with a recorded next hearing, active cases with no scheduled date, paginated case rows with court and status | Define active from existing status semantics with a shared named predicate. Derive next hearing from owned eligible Hearing rows and a documented status mapping. Verify alignment against dashboard and current case cards. Never count two hearings as two cases. |
| Calendar window | Hearing, Task, CaseEvent as tagged entries with record ID, case ID if present, day key, timing/status, safe label, provenance, and source reference | For hearings use aware IST start of day through start of day after the inclusive end. For Task.due_date and CaseEvent.date use plain dates. Exclude dismissed or undated tasks, keep completed dated tasks visible as done, and keep cancelled appointments consistent with the existing calendar's display and marker rules. |
| Open deadline focus | Eligible Task rows with due date, status, needs_review, due_date_basis, and an authorized source order reference when available | Include an unknown or review-required state in summaries where applicable. Use stored due dates and distinguish order directions, manual tasks, and limitation reminders. Keep calculations in the existing deadline service. |
| Selected case facts | Case identity, next hearing, selected recorded tasks, event metadata, and optional retrieved case-document snippets | Resolve the case under owner before querying related models. Apply owner and case checks to both joins and individual records. Supply only fields used for the current answer or draft. |

Start with a 7-day view and a 31-day maximum per calendar request, plus 25 rows per page and a 100 row hard cap for individual query results. Verify bounds and indexes with realistic fixtures. Return deterministic ordering, exact total where counted, pagination, as_of, timezone, and a truncation flag. Keep aggregate counts separate from page length. Handle colliding case names by prompting the user to choose a verified case, with case number and court for disambiguation. Use EXISTS, conditional aggregates, and bounded selects instead of per-case loops. Treat "none recorded" as a statement about Case Intel records. Never infer a court outcome, a date, or an external cause-list result from missing data.

Use a normalized reference object such as:

    {
      "kind": "hearing",
      "id": 18,
      "case_id": 104,
      "label": "Status hearing",
      "recorded_at": "2026-11-09T14:15:00+05:30"
    }

Keep identifiers numeric in the production contract. Construct frontend links from a fixed kind-to-route map. Never render URLs supplied by a model. Existing document citation fields stay compatible. Store typed practice references on the message via a validated versioned field or a related source model. Make history serialization preserve those references. Store document/page citations using existing citation infrastructure where it matches, and keep document revision provenance for draft inputs.

## 2. Dashboard and read-only assistant

- Add GET /api/practice-assistant/overview/?from=YYYY-MM-DD&to=YYYY-MM-DD for portfolio counts, the first page of case rows, and a bounded calendar agenda with explicit day markers. Use independently named cursors or separate read routes for further case and calendar pages. Use React Query keys that include range, kind filters, and authentication lifecycle. Clear practice state and caches on sign-out. Expose independent loading, empty, partial-data, and retry states so a chat failure cannot remove the calendar.
- Reuse lib/calendar.ts semantics, existing calendar row components when compatible, and existing day-picker patterns. Compare contract fixtures between the dashboard and /calendar. Keep the dashboard week selection, current range, and **Ask about this day** aligned. Clicking a day must not auto-send a message. Use the same normalized read result shape in the graph and agenda. Display the last updated time and correct handling of undated, completed, cancelled, and manual items.
- Mount the shared assistant/calendar section in the existing desktop briefing slot and mobile Dashboard branch. Keep the core controls visible inline. On smaller screens, use the app's existing sheet or expandable patterns for chat history and long results. Preserve view switching and keep focus/scroll predictable. Add source chips and a verified case chooser for handoff to the drafting studio. Treat an unverified case title from chat as display text until the server resolves an ID.
- Build a separate compiled practice graph using the same graph package and provider factory. Keep the existing case RAG graph independent. Proposed practice graph: validate scope → select an intent from a closed schema → run allowed typed read → present deterministic result or bounded synthesis → validate cited IDs. Use explicit UI actions for date and overview questions where possible. A classifier may propose intent and arguments for free text; validate the enum, date range, case ownership, and row limit on the server. Start with overview, calendar, open deadlines, missing next date, and selected case facts.
- Render exact counts/dates and easy answers from the read model first. If synthesis fails or returns unsupported references, return the structured result with a safe status. If the user's request needs data outside the available scope, offer a clarification or a case selection. Avoid arbitrary ORM/SQL execution and background court refreshes from the chat graph.
- Practice POST body: query, optional conversation_id, optional selected_day, and client_request_id. The server owns scope and as_of. Return existing-style answer and IDs plus intent, sources, structured summaries, as_of, and status (answer, needs_clarification, or partial). Record the request key per owner/scope and return the same turn on replay. Use existing retry UX. Store citations and user/assistant message IDs consistently across failed and successful calls.

## 3. Draft and note generation

### User contract and entities

The brief includes a verified case, output type, instructions, audience, tone, optional length, and selected sources. Include an optional user-supplied template selection in a later pass after validating its allowed fields and macros policy. Start with a status memo and a personal note. A prep-note template can use known hearing/date data. Start with English; add further languages only after font, content quality, and DOCX validation.

| Entity | Required fields and invariants |
| --- | --- |
| AssistantDraft | Owner, case, kind (document or note), subtype, status, request brief, optional origin conversation/message, current revision pointer, creation timestamps. Use owner and case indexes. Case change starts a new draft. |
| AssistantDraftRevision | Owner, parent draft, monotonic version, structured body, schema version, evidence refs and version/freshness fingerprints, missing required facts, validation warnings, editor provenance, creation timestamp. Immutable after save. Unique draft/version. |
| DraftApproval | Owner, exact revision, actor, approval time, content hash, source freshness marker, action kind. Keep approval tied to one immutable revision. Unique revision and action kind. |
| Draft output | Owner, approved revision, destination, status, file or note reference, safe error, timestamps. Unique revision/destination. Deterministic storage key for an export. |
| CaseNote | Owner, case, title, plain text or structured rich text, origin approval/revision, timestamps. New note rows can coexist with the case's existing notes field. Make later edits user-owned and auditable. |

Reuse OwnedModel and owner-scoped API patterns. Avoid copying full document content into revisions or message history. Store source IDs, version and page metadata, and only necessary approved text. Decide deletions for case, conversation, draft, revision, file, and note explicitly in model tests. Deleting a draft or conversation must not leave accessible orphan exports. Decide whether separately saved notes are retained as owned case records after deleting the originating draft, and show the effect in the UI.

### Graph branch and worker

Use a small drafting graph in core/services/graph/. Reuse existing owner-and-case-scoped retrieval and citation helpers where their contracts fit.

    resolve_case_and_brief
        -> collect_structured_case_facts
        -> retrieve_selected_case_documents
        -> generate_structured_draft
        -> validate_draft
        -> persist_preview_from_worker_result

The graph returns a structured candidate. The worker/application service persists it. Separate context collection from generation so owner checks, evidence assembly, and test fixtures remain deterministic. The selected documents are an additional hard retrieval constraint. For empty selection, use case-scoped retrieval only within the product's consent and context limits, or use verified case records alone when the request does not need documents. Clearly show the included sources in the UI. Never widen to portfolio retrieval during draft generation.

Suggested schema: title, subtype, sections with heading and blocks, evidence IDs per factual block, required verification items, optional warnings, and a generation version. Restrict block types to paragraph, bullet list, and simple table if necessary. Treat advocacy suggestions as suggestions rather than factual assertions. Keep recipient and other user-provided fields visibly marked as user input. Extract and verify legal/case facts against server-provided records. Label unresolved required fields explicitly. If a necessary fact is unavailable, return a reviewable draft with a gap or request clarification. Reject invented identifiers, unsafe markup, unsupported instructions, extra fields, and evidence outside the collected set. Validate structured output against server schema with a bounded repair attempt for providers returning imperfect JSON. Ensure the model can only propose content. Owner, case binding, approval, destinations, permissions, file writes, and job operations remain outside model control.

Use the existing ProcessingJob and process_jobs worker. Add a draft-generation job type with an explicit draft/request relationship, owner, and lane routing. Use a short transaction to create a draft plus queue row atomically when both are in the database. Release locks before calling the provider. Enforce a per-owner pending limit, timeout, context/token cap, and bounded retries. Define claim recovery for interrupted jobs using the queue's existing recovery semantics or a narrowly scoped lease and retry policy. When committing a preview, lock the draft and verify the job claim and expected generation/version. Late or duplicate completions cannot overwrite newer work. Use a fake provider for deterministic tests. Log job metadata, durations, retries and counts. Keep prompts, note bodies, raw order excerpts and client identities out of new logs and trace exporters. Existing chat logs include a query prefix. Review that path before sharing components with sensitive prompts.

### Approval and output

- Preview → edit → submit for review → approve exact revision → save note or export DOCX. User edits create a new immutable revision, with previous approval visible on the old revision only. Required facts, changed evidence, deleted sources, and unresolved verification items must be resolved or explicitly recorded as unknown where policy allows. Treat optional warnings distinctly from blockers.
- Implement approval as an authenticated Django transaction. Lock the draft, check owner, case and latest version, compare the requested revision and current expected version, revalidate required evidence, and store actor/time/hash. Return 409 when the preview is stale or source data has materially changed. Never approve by interpreting model text or a chat message. Preview and approval survive refresh and worker restarts.
- First release uses Django persistence for pending review. The initial graph finishes when its candidate validates, and approval is a separate user request. This keeps the existing LangGraph dependency and avoids introducing checkpoints just to wait on an approval. If a later workflow genuinely needs in-graph pause/resume, verify a compatible persistent checkpointer against the pinned stack, derive an opaque server-owned thread ID per owner and draft, test restart and replay, and keep side effects outside the interrupted node or idempotent. LangGraph resumes an interrupted node from its beginning. [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) · [Durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution) · [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- Render DOCX deterministically with python-docx from the approved schema. Use controlled styles, page breaks, case metadata, sanitized filenames, and draft/provenance labeling as appropriate. Test actual paragraphs, tables, page citations, headers, and Unicode. Keep preview editable through the approved revision flow. Reuse private Django storage patterns and authenticated downloads. Reserve an output row by approved revision and destination, then write storage under a stable revision-specific key with checksum. Use retry-safe state transitions and cleanup of abandoned files on partial failure. Download returns only ready outputs after rechecking ownership.
- Store a personal note in the new owner-scoped CaseNote using the exact approved revision. Use an atomic save and a unique revision link to handle repeat clicks. Show it under case detail Notes. Keep generated documents available in draft history. If a later release adds **Attach to case documents**, make it an explicit action and preserve generated provenance. Decide whether generated attachments should enter retrieval, because unreviewed or generated text must never silently become evidence for subsequent drafts.

### Proposed draft API

Use positive integer IDs or opaque UUIDs consistently with existing conventions. Every mutation checks authentication, owner, case, state, expected version, and allowed action. Creation/revision/output actions use an idempotency key scoped to owner and operation. A reused key with a different payload returns 409.

| Method and route | Result |
| --- | --- |
| POST /api/case-assistant/drafts/ | Validate case and brief, enqueue generation, return 202 plus draft and job state. |
| GET /api/case-assistant/drafts/{id}/ | Owner-scoped status, current preview, validation, source links, approved revision, and available outputs. |
| POST /api/case-assistant/drafts/{id}/revisions/ | Persist edited content under expected_revision. Revalidate with the same schema. Return 201 or 409. |
| POST /api/case-assistant/drafts/{id}/approve/ | Approve exact revision ID, requiring the current revision and evidence state. Repeat of the same action returns the existing approval. |
| POST /api/case-assistant/drafts/{id}/outputs/ | Request DOCX or note save for exact approved revision. Return an existing result on replay, or 202 for queued export. |
| GET /api/case-assistant/outputs/{id}/download/ | Owner-checked binary response for ready DOCX. Return an owner-scoped note reference from note outputs. |
| POST /api/case-assistant/drafts/{id}/retry/ | Retry a recoverable failure under the same draft and validated case. Return active job instead of duplicating it. |

For concurrent edits, use expected revision in API requests, database uniqueness constraints, and transactional row locks. Handle stale edit, missing source, no provider, rate limit, worker timeout, cancellation, invalid draft, and storage failure with actionable messages. Avoid a network round trip for every keystroke. Use a clearly labeled save/submit action and a leaving-page warning only while there are unsaved edits.

## 4. Phased delivery and acceptance

| Phase | Work and dependency | Acceptance gate |
| --- | --- | --- |
| A. Scope and evidence | Add scope migration, source serializers and tests. Build bounded portfolio/calendar reads. | Existing case and legacy document chats behave as before. User A cannot read B's records through chat, history, search, source links or filters. Counts agree with fixtures and the IST calendar. |
| B. Dashboard beta | Add overview endpoint, compact calendar, scoped practice graph and UI behind the existing frontend flag and a backend gate. | Both desktop and mobile show the calendar and assistant. An explicit selected date and its answer share a read model. Empty, truncated and unavailable results are legible and source links resolve. |
| C. Draft preview beta | Add draft/revision storage, generation jobs, case brief UI, citations and validation. | A case selection is mandatory. An editable sample memo and personalized note survive reload, and generation retries do not create duplicate revisions. Wrong-case source IDs and injected instructions in documents fail safely. |
| D. Approval and release | Add approval service, approved note and DOCX outputs, download permissions, cleanup and audit events. | Double approval/export yields one outcome. Editing a prior approval cannot release newer text. Download bytes and saved note match the approved revision. Case and user authorization is enforced at every stage. |

### Implementation and test checklist

- Keep portfolio and drafting feature flags independent. Run migration and deploy-compatible workers before enabling endpoints, then enable the UI. Check lane allowlists and the staging worker's ability to drain jobs. An off switch should prevent new runs while leaving approved outputs accessible under existing permissions. Follow repo conventions on deployment configuration.
- Backend unit tests: resolver, bounded queries, exact totals and pagination, status cases, source shape, closed intent schema, missing facts, invalid JSON/repair, source grounding, and rendering fixtures. Include scheduled eCourts day, manual hearing at 00:30 IST, null due date, completed/dismissed task, cancelled appointment, exact range end, empty case and no next hearing. Use fake clock and providers.
- PostgreSQL integration: two owners, duplicate case titles, foreign case/conversation/message/source/draft/version/output IDs, forged request owner, stale revisions, concurrent approvals, worker claim/retry/recovery and storage compensation. Verify revalidation when a source is modified or deleted. Extend existing tenant endpoint discovery tests and local-DB guard.
- Frontend tests: desktop and mobile entry points, loading/empty/error, calendar/date/source handoff, chat history isolation, editing and conflict responses, case switching, approval invalidation, and download errors. Add Playwright scenarios against mock APIs. Verify keyboard focus, screen-reader labels, 320 px reflow and auth cache clearing.
- Regression and release checks: run targeted pytest with local PostgreSQL and pgvector, existing chat and tenancy tests, and the repo frontend install/build/lint checks. Use a seeded local demo and verify a DOCX in Word or LibreOffice. Verify flags off, mixed-version worker rollout, and recovery from a cancelled or interrupted job. Keep metrics limited to latency, queue depth, failure class, usage counts, and payload sizes.
- Punctuation for new authored UI copy: use sentence punctuation, labels or whitespace in place of em dashes. Preserve quoted source material and advocate-entered text as recorded.

### Decisions for the implementation agent

Start with one advocate per authenticated owner, the existing three calendar sources, English DOCX, and independent personal case notes. Confirm the exact definition of active in product copy, case note placement, and retention/deletion policy before production enablement. The suggested date and pagination limits are starting values. Measure with real-shaped fixtures and adjust within a bounded contract. Deliver each phase with the associated acceptance tests and a short description of schema/API changes, migration order, and feature-flag rollback.
