# Conversation History, Export, and Chat UI Changes

## Scope

This document captures:

1. The initial investigation findings before implementation.
2. The backend and frontend changes that were made.
3. The verification work completed afterward.

## Part 0: Investigation Findings

### 1. Existing conversation list endpoint

An endpoint already existed:

- URL: `/api/conversations/`
- Filtered example: `/api/conversations/?case_id=<case_id>`
- URL registration: `core/urls.py`
- View: `core/views/conversation.py` -> `ConversationListView`

What it did before this change:

- Listed conversations.
- Allowed optional `case_id` filtering.
- Returned `id`, `case_id`, `title`, `started_at`, `last_message_at`, and `message_count`.
- Did **not** include a preview field.

### 2. Existing conversation history endpoint

There was no dedicated `/api/conversations/<id>/messages/` endpoint before this work.

What did already exist:

- URL: `/api/conversations/<id>/`
- URL registration: `core/urls.py`
- View: `core/views/conversation.py` -> `ConversationDetailView`
- Serializer: `core/serializers/conversation.py` -> `ConversationDetailSerializer`

That existing detail endpoint already returned:

- Conversation metadata.
- Nested `messages`.
- Each message's citations.

So full message history was already fetchable, but only through the detail endpoint and not via a dedicated messages route.

### 3. Was `Conversation.title` being populated?

Yes.

Before this change, `Conversation.title` was already being set in:

- `core/services/ai_workflow.py` -> `AIWorkflowService._get_or_create_conversation()`

The prior behavior:

- New conversations used `query[:100]` as the title.
- Fallback title was `"New Conversation"` if the incoming query was empty.

Live database check during investigation:

- Total conversations: `24`
- `title IS NULL`: `0`
- `title = ''`: `0`
- Conversations with messages and missing titles: `0`

So the title field was **not** staying null in the current dev data. The gap was not "no title generation exists"; the gap was that title generation was simplistic and there was no backfill mechanism for older null/blank records if they ever existed elsewhere.

### 4. Frontend chat flow before implementation

The frontend was holding the active conversation only in local component state:

- File: `frontend-next/components/chat/chat-panel.tsx`
- State: `const [conversationId, setConversationId] = useState<number | null>(null);`

Before this change:

- Sending a message posted `conversation_id: conversationId || undefined`.
- If no `conversationId` was present in current component state, the request effectively started a new conversation.
- The frontend only stored the returned `conversation_id` in memory for that mounted chat panel instance.
- There was no history sidebar or reload mechanism connected to the existing conversations API.
- `frontend-next/hooks/use-chat.ts` had conversation hooks, but they were not used by the case chat UI.
- After refresh, navigation away, or chat-panel remount, there was no in-UI way to restore a previous conversation.

Conclusion:

- Existing conversations were persisted in the backend.
- The UI effectively behaved like "single in-memory session unless you manually stay on the page."

## Backend Changes

### Conversation API

Updated `GET /api/conversations/?case_id=<id>` to return richer history metadata:

- `id`
- `case_id`
- `title`
- `started_at`
- `last_message_at`
- `message_count`
- `preview`

Implementation details:

- Added a first-user-message annotation in `core/views/conversation.py`.
- Added serializer fallback logic in `core/serializers/conversation.py` so blank/null titles are displayed as generated titles instead of surfacing empty entries.

### Dedicated message history endpoint

Added:

- `GET /api/conversations/<id>/messages/`

This returns the ordered full message history with:

- `role`
- `content`
- `created_at`
- `citations`

### Auto-titling improvements

Added shared title helpers in:

- `core/services/conversation_utils.py`

New behavior:

- Titles are generated from the first user message.
- Truncation targets roughly 50 characters.
- Trailing partial words are trimmed cleanly when possible.

Updated:

- `core/services/ai_workflow.py`

So new conversations now use the improved title generator instead of raw `query[:100]`.

### Backfill migration

Added migration:

- `core/migrations/0007_backfill_conversation_titles.py`

Purpose:

- Backfills blank/null conversation titles from the first user message.
- Uses `"New Conversation"` only when no usable message text exists.

### Export endpoint

Added:

- `GET /api/conversations/<id>/export/?format=txt|md|pdf`

Behavior:

- Defaults to `txt` when `format` is missing or invalid.
- Returns a direct download via `Content-Disposition`.
- Sanitizes filenames for Windows-safe output.

Supported formats:

- `txt`: plain transcript with case, title, export timestamp, turn labels, and source filenames.
- `md`: markdown transcript with the same structure while preserving stored assistant markdown/body formatting.
- `pdf`: generated PDF transcript using Pillow, with formatted pages, clear speaker distinction, and source filenames.

### Duplicate sources cleanup for export

The export helpers remove a trailing embedded `Sources:` section from stored assistant text before re-listing sources from citation records. This prevents exported transcripts from duplicating sources while leaving the retrieval/citation-generation pipeline untouched.

### Chat safety improvement

Updated `core/views/chat.py` so that:

- Unknown `conversation_id` returns `404` instead of silently creating a new conversation.
- A conversation belonging to a different case returns `400`.

This protects the "continue the selected conversation" behavior from accidental silent forks.

## Frontend Changes

### Case chat workspace

Refactored:

- `frontend-next/components/chat/chat-panel.tsx`
- `frontend-next/app/(dashboard)/cases/[id]/page.tsx`

The chat area now behaves as a history-aware workspace instead of a single ephemeral message box.

### Conversation history UI

Added a case-scoped history sidebar inside the chat view:

- Lists prior conversations for the current case.
- Shows title, last-message timing, and preview.
- Loads the selected conversation's full message history.

### Explicit New Chat behavior

Added an explicit `New Chat` action.

New behavior:

- A new conversation is only created after the user explicitly starts a draft chat and sends the first message.
- If no conversation is selected and no draft is active, the input is disabled with clear guidance.

### Continue existing conversations

When a history item is selected:

- The message history is loaded from `/api/conversations/<id>/messages/`.
- New sends use that same `conversation_id`.
- The next message continues the conversation rather than starting a new one.

### Export UI

Added export controls in the chat header:

- Format selector: `txt`, `md`, `pdf`
- Export button

Frontend API additions:

- `frontend-next/lib/api/chat.ts` now supports:
  - `getMessages(id)`
  - `export(id, format)`

### Loading and thinking state

Improved the waiting state:

- Existing basic typing indicator was replaced with a clearer "AI is working on your answer" status.
- Added elapsed-seconds feedback during long-running responses.

### Error handling and retry

Added visible request failure handling:

- Inline error state in the chat header.
- `Retry Last Message` button.
- No more silent request failure with only a console error.

### Duplicate sources rendering fix

The chat renderer now strips a trailing embedded `Sources:` section from assistant message content before separately rendering the citations block. This ensures sources appear exactly once per assistant message.

### Supporting API/type changes

Updated:

- `frontend-next/types/chat.ts`
- `frontend-next/lib/api/client.ts`
- `frontend-next/lib/api/chat.ts`

To support:

- conversation previews
- conversation export formats
- message-history fetches
- download handling

## Verification Completed

### Backend verification

Automated backend tests were added and passed:

- `python manage.py test core.tests.test_conversation_api`

Covered cases:

- conversation list filtering and previews
- title fallback behavior
- dedicated messages endpoint
- txt/md/pdf export endpoint behavior
- invalid-format fallback to txt
- rejection of unknown `conversation_id` on chat POST

### Live local endpoint verification

Verified against the running local backend:

- `GET http://localhost:8000/api/conversations/?case_id=4`
- Response included:
  - `title`
  - `last_message_at`
  - `preview`
  - `message_count`

### Frontend verification constraints

The local frontend responded on:

- `http://localhost:3000`

I could not do in-session visual browser automation because no browser instance was available to the Codex browser runtime in this session. The browser runtime initialized successfully, but `agent.browsers.list()` returned an empty list.

### Build/type-check findings

Backend:

- Targeted backend tests pass.

Frontend:

- A full `next build` from this environment hit a Windows sandbox `spawn EPERM`.
- A project-wide TypeScript run also surfaces unrelated pre-existing frontend errors in email/dashboard files outside this feature area.

Because of those pre-existing frontend issues, scoped feature verification relied on:

- live endpoint checks
- backend automated tests
- your manual `npm run dev` validation that the new features are present

## Files Added

- `core/services/conversation_utils.py`
- `core/migrations/0007_backfill_conversation_titles.py`
- `core/tests/__init__.py`
- `core/tests/test_conversation_api.py`
- `frontend-next/tsconfig.chat-panel.json`
- `documentations/CONVERSATION_HISTORY_EXPORT_UI_CHANGES.md`

## Files Modified

- `core/serializers/conversation.py`
- `core/services/ai_workflow.py`
- `core/urls.py`
- `core/views/__init__.py`
- `core/views/chat.py`
- `core/views/conversation.py`
- `frontend-next/app/(dashboard)/cases/[id]/page.tsx`
- `frontend-next/components/chat/chat-panel.tsx`
- `frontend-next/lib/api/chat.ts`
- `frontend-next/lib/api/client.ts`
- `frontend-next/types/chat.ts`

## Notes

- The retrieval/RAG pipeline, LangGraph flow, and citation-generation logic were left intact.
- The changes were focused on the conversation-history layer, export layer, and chat UI behavior.
