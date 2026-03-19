# Case Intel - Project Memory

## Project Overview

- Django 6.0.3 + DRF + PostgreSQL (pgvector) + LangGraph + OpenAI
- Legal case management platform with AI-powered document search and Q&A

## Key Architecture

- **Models** (14): `core/models/` — Case, Document, DocumentChunk (pgvector 1536d), Conversation, Message, Citation, etc.
- **AI Services**: `core/services/` — LLMClient, EmbeddingService, VectorSearchService, DocumentProcessor, AIWorkflowService
- **LangGraph Pipeline**: `core/services/graph/` — state.py (AgentState), nodes.py (9 nodes), builder.py, config.py
- **API Layer**: `core/views.py` (Chat, Cases, Conversations, Documents), `core/serializers.py`, `core/urls.py`
- **Admin**: All models registered in `core/admin.py`

## LangGraph Flow

```
route_query → analyze_query → vector_search → rank_chunks → generate_answer → extract_citations → format_response
                                    ├── handle_no_results (chunk_count=0)
                                    └── handle_low_confidence (score < threshold)
```

## API Endpoints (prefixed /api/)

- `POST /api/chat/` — AI query processing
- `GET|POST /api/cases/`, `GET|PATCH|DELETE /api/cases/<id>/`
- `GET /api/conversations/`, `GET|DELETE /api/conversations/<id>/`
- `GET /api/documents/`, `GET|DELETE /api/documents/<id>/`
- `POST /api/documents/upload/` (multipart), `POST /api/documents/<id>/process/`

## Configuration

- All AI config via env vars: OPENAI_API_KEY, OPENAI_MODEL (gpt-4o), OPENAI_EMBEDDING_MODEL (text-embedding-3-small)
- DB config via env vars: DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT
- Embedding dimensions: 1536 (must match DocumentChunk.embedding VectorField)

## Branch: workflow_setup (current), main (base)
