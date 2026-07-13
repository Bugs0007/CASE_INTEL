# Case Intel

Legal case management platform with AI-powered document search and Q&A over uploaded case documents.

## Stack

- **Backend:** Django 5.1.11 (pinned — see Gotchas) + Django REST Framework 3.17, `core` is the only app
- **DB:** PostgreSQL with `pgvector` (RDS in production)
- **AI:** LangGraph 0.6.11 pipeline via a factory pattern. LLM (chat generation) provider is independently configurable — Groq, Ollama, or OpenAI. Embedding provider is Ollama-only right now (`nomic-embed-text`, 768-dim); OpenAI embeddings exist as a fallback path but Gemini/other embedding providers were deliberately not implemented.
- **Frontend:** `frontend-next/` — Next.js 15 / React 19 / TypeScript / Tailwind, deployed on Vercel
- **Async/cache:** Celery + Redis (`django_celery_beat`, `django_celery_results`)
- **Config:** `python-decouple`, all environment-dependent settings must be read via `config(...)` in `case_intel_project/settings.py` — never hardcode `DEBUG`, `ALLOWED_HOSTS`, `SECRET_KEY`, DB credentials, or API keys directly in source.

## Architecture

- **Models** — `core/models/`: `Case`, `Hearing`, `Document`, `DocumentChunk`, `Conversation`, `Message`, `Citation`, `Folder`, `Email`, etc. All registered in `core/admin.py`.
- **AI services** — `core/services/`: `ai_service_factory.py` has two independent toggles. `get_llm_client()` checks `USE_GROQ` first (routes to `LLMClient` with Groq's OpenAI-compatible `base_url`), then `USE_OLLAMA` (`OllamaLLMClient`), then falls back to OpenAI (`LLMClient` with no `base_url` override). `get_embedding_service()` only checks `USE_OLLAMA` — `OllamaEmbeddingService` or OpenAI's `EmbeddingService` — and is untouched by `USE_GROQ`.
- **LangGraph pipeline** — `core/services/graph/` (`state.py`, `nodes.py`, `builder.py`). Current flow (lean 3-node, rewritten from an earlier 9-node version — see `builder.py` docstring for the rationale, ~8-12s latency, 2 LLM calls/query):

  ```
  hyde_expand → hybrid_search → generate_answer → END
  ```

- **Views/serializers** — `core/views/`, `core/serializers/`, both modular packages split by domain (chat, case, conversation, document, hearing, gmail, email, folder, dashboard).
- **URLs** — `core/urls.py`, all endpoints mounted under `/api/`.

## API Endpoints (all under `/api/`)

`dashboard/`, `chat/`, `conversations/`, `conversations/<id>/`, `conversations/<id>/messages/`, `conversations/<id>/export/`, `cases/`, `cases/<id>/`, `hearings/`, `hearings/<id>/`, `documents/`, `documents/<id>/`, `documents/upload/`, `documents/<id>/process/`, `folders/`, `gmail/auth/`, `gmail/callback/`, `gmail/status/`, `gmail/sync/`, `emails/`, `emails/<id>/link/`

Note: `gmail/callback/` is hit directly by Google's OAuth redirect (not a token-authenticated frontend call) — keep that in mind if endpoint auth requirements change.

## Deployed infrastructure

- **Backend:** AWS EC2 (`13.204.122.149`), also reachable via `caseintel.duckdns.org` for HTTPS
- **DB:** AWS RDS Postgres, `case-intel-db.cru26wowwqp8.ap-south-1.rds.amazonaws.com`
- **Frontend:** Vercel, production domain `case-intel.vercel.app`, plus per-deployment preview URLs of the form `case-intel-<hash>-bhagath-personal-projects.vercel.app`

## Common commands

```bash
# Backend (from repo root, with venv active)
python manage.py runserver
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py check              # sanity-check settings before anything else

# Frontend (from frontend-next/)
npm run dev
npm run build
npm run lint
```

There is currently **no automated test suite** in this repo (no `test*.py` files under `core/`). Don't assume `manage.py test` exercises anything.

## Gotchas

- **Django is pinned to 5.1.11** — do not upgrade. A newer Django version conflicts with `django-celery-beat` as installed here. Check `requirements.txt` compatibility before ever touching this pin.
- **`DEBUG` / `ALLOWED_HOSTS` / `SECRET_KEY` must come from `.env` via `python-decouple`**, not be hardcoded. (`SECRET_KEY` was hardcoded in source until this was fixed — if you see a hardcoded fallback default in `settings.py`, that's intentional for local-dev-without-`.env` convenience, not a place to put real secrets.)
- **Embedding dimensions are NOT fully dynamic.** `settings.py` computes `EMBEDDING_DIMENSIONS` dynamically based on `USE_OLLAMA` + the configured model (768 for Ollama `nomic-embed-text`, 1536 for OpenAI `text-embedding-3-small`), but `core/models/document_chunk.py`'s `DocumentChunk.embedding` field is **hardcoded** to `VectorField(dimensions=768)`. If you switch `USE_OLLAMA` to `false` and OpenAI's embedder is actually invoked, embedding writes will fail or silently mismatch against the fixed 768-dim column/HNSW index. A real migration (changing the field + re-embedding existing chunks) is required to actually switch providers in a running deployment — flipping the env var alone is not sufficient.
- **CORS/auth are different domains** — Vercel frontend and EC2 backend are cross-origin. Prefer token-based auth over cookies to sidestep cross-domain cookie issues.
- `.env` is gitignored and has never been committed — keep it that way. Never put real secrets directly into `settings.py` defaults.
- **`USE_GROQ` only affects chat generation, never embeddings.** Embeddings always go through Ollama's `nomic-embed-text` regardless of `USE_GROQ` — this is intentional (Groq doesn't serve `nomic-embed-text`, and no other embedding provider has been wired in). Even in a `USE_GROQ=true` deployment, Ollama must still be installed and running for embeddings to work at all.
- **No production `GROQ_API_KEY` exists yet.** The key used to verify this integration was a local-testing-only key. Before `USE_GROQ=true` can go live, generate a dedicated production key in the Groq console (console.groq.com/keys) and add it to prod `.env` — do not reuse the dev/test key for production. Also see the Ollama-on-EC2 gap noted for the same deploy (Ollama isn't installed on the EC2 instance yet, and embeddings need it regardless of `USE_GROQ`).
