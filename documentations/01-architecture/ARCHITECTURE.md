# Architecture

This document describes the current implemented architecture in this repository.

## Stack

- Frontend: Next.js 15 App Router, React 19, React Query, Tailwind CSS
- Backend: Django 6.0.3, Django REST Framework
- Database: PostgreSQL with `pgvector`
- Local AI path: Ollama via `ollama` and `langchain-ollama`
- Fallback AI path: OpenAI SDK clients behind `USE_OLLAMA=false`
- Workflow orchestration: `langgraph`

## Repository Shape

- `frontend-next/`: the active frontend
- `core/models/`: domain models
- `core/views/`: REST API endpoints
- `core/serializers/`: request/response validation
- `core/services/`: document processing, AI orchestration, Gmail integration, vector search
- `case_intel_project/`: Django settings and URL wiring

There is no `frontend/` directory in the current repo root, and `case_intel_project/urls.py` only mounts `/api/` routes from Django. The in-repo UI is the Next.js app.

## Frontend Architecture

The current frontend is a dashboard-style Next.js application:

- `app/(dashboard)/page.tsx`: dashboard
- `app/(dashboard)/cases/page.tsx`: case list
- `app/(dashboard)/cases/[id]/page.tsx`: case detail, hearing list, chat slide-out
- `app/(dashboard)/documents/page.tsx`: documents
- `app/(dashboard)/emails/page.tsx`: Gmail/email page

Shared API access lives under `frontend-next/lib/api/`, and React Query hooks live under `frontend-next/hooks/`.

### Current Chat UX

The checked-in chat experience is a slide-out `ChatPanel` opened from a case detail page:

- sends requests to `POST /api/chat/`
- keeps `conversation_id` in component state while the panel remains open
- shows a typing/loading indicator
- appends a generic assistant error message when the request fails
- supports starting over by clearing local state

What is not present in the checked-in frontend:

- no conversation-history sidebar in the case chat UI
- no export button for txt/md/pdf transcripts
- no dedicated retry action in the chat panel

## Backend Architecture

### Core Domain Areas

- Case management
- Document upload and processing
- Vector search over chunk embeddings
- Conversation/message/citation persistence
- Gmail credential storage and email sync
- Dashboard aggregation

### Document Processing Flow

`DocumentProcessView` calls `DocumentProcessor.process_document()` synchronously:

1. mark document as `processing`
2. extract text from PDF, DOCX, DOC, or TXT
3. chunk text
4. generate embeddings through the active embedding provider
5. write `DocumentChunk` rows
6. mark document as `completed` or `failed`

The current view layer does not enqueue this work onto Celery.

### Vector Search

`VectorSearchService` uses `pgvector.django.CosineDistance` against `DocumentChunk.embedding` and optionally filters by `case_id` and document type.

## AI Runtime Configuration

`case_intel_project/settings.py` and `.env.example` currently default to Ollama:

- chat model: `llama3.1:8b`
- embedding model: `nomic-embed-text`
- embedding dimension setting for that model: `768`

`core/models/document_chunk.py` hardcodes `VectorField(dimensions=768)`, so the database schema currently matches the Ollama embedding path, not the 1536-dimension OpenAI default.

### OpenAI Status

OpenAI support still exists in code:

- `core/services/llm_client.py`
- `core/services/embedding_service.py`
- `core/services/ai_service_factory.py`

But this pass only verified the local Ollama-configured path. Treat OpenAI as a maintained fallback path in code, not as the verified default runtime.

## LangGraph Workflow

The current `core/services/graph/builder.py` defines a 9-node graph, not a 3-node graph:

1. `route_query`
2. `analyze_query`
3. `vector_search`
4. `rank_chunks`
5. `generate_answer`
6. `extract_citations`
7. `format_response`
8. `handle_no_results`
9. `handle_low_confidence`

Conditional routing:

- `route_query` either ends immediately for clarification or continues to `analyze_query`
- `vector_search` routes to `handle_no_results`, `handle_low_confidence`, or `rank_chunks`

## Conversation Persistence

Conversation state is backed by database models:

- `Conversation`
- `Message`
- `Citation`

Current API coverage:

- `GET /api/conversations/`
- `GET /api/conversations/{id}/`
- `DELETE /api/conversations/{id}/`
- `POST /api/chat/`

Current gaps relative to earlier feature requests:

- no `/api/conversations/{id}/messages/`
- no `/api/conversations/{id}/export/`
- conversation list entries return `message_count`, not first-message previews

## Feature Maturity Snapshot

### Working End-to-End

- case CRUD
- document upload
- synchronous document processing
- case-scoped chat requests
- conversation list/detail retrieval
- dashboard summary endpoint

### Present But Partial

- hearings UI exists, but add/edit/delete actions are not wired in the visible component
- Gmail/email UI is reachable, but several frontend assumptions do not match the backend contract
- activity feed UI is reachable, but the dev database currently has no `ActivityLog` rows

## Infrastructure

The project includes configuration for:

- Redis cache
- Celery worker
- `django_celery_beat`
- `django_celery_results`

Those pieces are installed and migrated, but the current verified UI/API flows do not depend on background task dispatch to function locally.
