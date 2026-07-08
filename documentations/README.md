# Case Intel Documentation

This folder is the verified documentation set for the current repository state as checked on July 4, 2026. The files linked here were rewritten against the code in `core/`, `case_intel_project/`, and `frontend-next/` rather than copied forward from older summaries.

## Current State Snapshot

- Frontend: Next.js 15 app in `frontend-next/`
- Backend: Django 6 + Django REST Framework
- Retrieval store: PostgreSQL + pgvector
- Default AI path: Ollama with `llama3.1:8b` for chat and `nomic-embed-text` for embeddings
- Fallback AI path: OpenAI clients exist behind `USE_OLLAMA=false`, but this documentation pass only verified the Ollama-configured local path
- LangGraph workflow: 9 nodes in the checked-in `core/services/graph/builder.py`
- Chat persistence: `Conversation`, `Message`, and `Citation` are live models with list/detail API support
- Not in the checked-in API: conversation export endpoints and a dedicated `/api/conversations/{id}/messages/` route

## Verified Feature Verdicts

These four items were marked "Complete" in the old `PROJECT_OVERVIEW.md` feature matrix. The code does not support that claim.

| Feature | Reachable UI in `frontend-next/` | Backend works end-to-end | Dev DB data | Verdict |
| --- | --- | --- | --- | --- |
| Hearing Management | Yes, as `HearingsList` on case detail pages | CRUD endpoints exist and `/api/hearings/` returns live data | `hearings` table is empty | `scaffolded but non-functional` |
| Gmail OAuth | Yes, on `/emails` | Status/auth endpoints exist, but frontend callback/disconnect assumptions do not match backend | `gmail_credentials` has 1 row | `scaffolded but non-functional` |
| Email Sync | Yes, on `/emails` | Sync/list/link endpoints exist, but frontend request/response expectations are out of sync with the API | `emails` has 49 rows | `scaffolded but non-functional` |
| Activity Feed | Yes, on dashboard | Dashboard endpoint returns `recent_activity` | `activity_logs` table is empty | `scaffolded but non-functional` |

## Read This First

- [QUICKSTART.md](./QUICKSTART.md)
- [01-architecture/ARCHITECTURE.md](./01-architecture/ARCHITECTURE.md)
- [02-reference/API_CONTRACTS.md](./02-reference/API_CONTRACTS.md)
- [02-reference/DB_SCHEMA.md](./02-reference/DB_SCHEMA.md)
- [03-setup/OLLAMA_SETUP.md](./03-setup/OLLAMA_SETUP.md)
- [04-interview-prep/INTERVIEW_FAQ.md](./04-interview-prep/INTERVIEW_FAQ.md)

## Planning Docs

These are intentionally future-scope documents, not claims about the implemented system:

- [05-future-scope/COURT_FETCHING_SYSTEM_DESIGN.md](./05-future-scope/COURT_FETCHING_SYSTEM_DESIGN.md)
- [05-future-scope/DESKTOP_APP_PACKAGING.md](./05-future-scope/DESKTOP_APP_PACKAGING.md)

## Legacy / Auxiliary Files

The official current-state docs are the files linked above. Any retained extras in `documentations/` such as `SYSTEM_DESIGN.md` or schema image assets should be treated as archival material unless this README links to them directly.
