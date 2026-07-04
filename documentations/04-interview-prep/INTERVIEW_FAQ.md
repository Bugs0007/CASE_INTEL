# Interview FAQ

This FAQ is tuned to what the code actually does today, so you can talk about the project honestly.

## What is Case Intel?

Case Intel is a local-first legal case workspace that combines case tracking, document ingestion, semantic search over uploaded documents, and an AI chat interface that stores conversations and citations.

## What stack did you use?

- Next.js 15 + React 19 for the frontend
- Django 6 + DRF for the backend API
- PostgreSQL + pgvector for data and vector search
- Ollama for the default local LLM and embedding runtime
- LangGraph for multi-step AI orchestration

## How does the AI pipeline work?

The current checked-in LangGraph flow has 9 nodes:

1. `route_query`
2. `analyze_query`
3. `vector_search`
4. `rank_chunks`
5. `generate_answer`
6. `extract_citations`
7. `format_response`
8. `handle_no_results`
9. `handle_low_confidence`

It is not a 3-node HyDE pipeline in the current repo. The graph classifies the question, extracts filters, runs pgvector search, reranks chunks with the LLM, generates an answer, extracts citations, and formats the final response.

## What embedding model are you using?

The current default embedding model is Ollama `nomic-embed-text`, and the database schema stores vectors at 768 dimensions. That is enforced both in settings and in `DocumentChunk.embedding`.

## Are you using OpenAI or Ollama?

The default configured runtime is Ollama:

- `OLLAMA_MODEL=llama3.1:8b`
- `OLLAMA_EMBEDDING_MODEL=nomic-embed-text`
- `USE_OLLAMA=true`

OpenAI support still exists as a code path, but if you are describing the verified local setup, say the project currently runs on Ollama by default and OpenAI is fallback code, not the actively documented runtime.

## What does the frontend look like today?

The frontend is a Next.js 15 dashboard app in `frontend-next/`. It includes:

- dashboard
- cases list
- case detail pages
- document management
- email integration page
- slide-out AI chat panel on case detail pages

Do not describe the frontend as a vanilla `index.html` app. That is from older docs and is not the active repo structure.

## How does chat persistence work?

The backend saves:

- `Conversation`
- `Message`
- `Citation`

The current API supports:

- `POST /api/chat/`
- `GET /api/conversations/`
- `GET /api/conversations/{id}/`
- `DELETE /api/conversations/{id}/`

If asked about exports or a dedicated message-history endpoint, be careful: those routes are not present in the current checked-in URLconf.

## What parts are production-ready versus partial?

Safe, accurate framing:

- case CRUD, document upload, synchronous document processing, vector search, and case-scoped chat are implemented
- Gmail/email, hearings, and activity feed are partially implemented and visible in the UI, but not fully polished end-to-end
- the project has real data for synced emails and Gmail credentials, but hearings and activity logs are empty in the dev database

## Why did you choose PostgreSQL + pgvector instead of a separate vector database?

It keeps the stack simple for a local-first app:

- document metadata and vectors live in one database
- case-based filtering stays straightforward
- deployment and local setup stay smaller than a split SQL + vector system

## What is one good “walk me through a request” answer?

When a user asks a question from a case page, the frontend posts to `/api/chat/` with the case ID and optional conversation ID. The backend loads recent conversation history, runs the LangGraph workflow, performs pgvector search over `DocumentChunk` embeddings, generates the answer, persists the assistant message plus citations, and returns the answer metadata back to the Next.js UI.

## Behavioral / Project Journey

### What was the most challenging part of this project?

The hardest part was turning a legal-document workflow into something reliable enough to demo honestly. It was not just “call an LLM.” I had to think about ingestion, chunking, embeddings, search quality, citation traceability, and how to persist enough conversation state for the tool to feel useful instead of stateless.

### What would you do differently if starting over?

I would lock the API contracts and feature status docs much earlier. A lot of confusion in this codebase came from the implementation moving forward faster than the documentation, especially around frontend expectations versus backend response shapes.

### What did you learn from this project?

I learned that retrieval quality and product honesty matter more than flashy AI framing. It is easy to make a demo look more complete than it really is, but much harder and more valuable to build a system where you can explain exactly what is implemented, what is partial, and why.

### How would you improve this project next?

- finish the partial Gmail/email/hearing flows end-to-end
- tighten the frontend/backend contracts with shared schemas
- add stronger automated tests around chat, document processing, and email sync
- decide whether to keep synchronous document processing or move it fully onto Celery

## Key Commands

```powershell
.\.venv\Scripts\python.exe manage.py runserver 8000
cd frontend-next; npm run dev
ollama serve
```

## Good Honesty Checks For Interviews

- Do not say the app has a 3-node graph unless you have re-verified the code.
- Do not say the app still serves a vanilla frontend.
- Do not say hearings, Gmail OAuth, email sync, or activity feed are fully complete in the current repo.
