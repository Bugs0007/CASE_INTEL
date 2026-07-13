# Case Intel

Legal case management platform with AI-powered document search and Q&A over uploaded case documents.

## Stack

- **Backend:** Django 5.1.11 (pinned — see Gotchas) + Django REST Framework 3.17, `core` is the only app
- **DB:** PostgreSQL with `pgvector` (RDS in production)
- **AI:** LangGraph 0.6.11 pipeline, routed at runtime to either Ollama (local) or OpenAI via a factory pattern
- **Frontend:** `frontend-next/` — Next.js 15 / React 19 / TypeScript / Tailwind, deployed on Vercel
- **Async/cache:** Celery + Redis (`django_celery_beat`, `django_celery_results`)
- **Config:** `python-decouple`, all environment-dependent settings must be read via `config(...)` in `case_intel_project/settings.py` — never hardcode `DEBUG`, `ALLOWED_HOSTS`, `SECRET_KEY`, DB credentials, or API keys directly in source.

## Architecture

- **Models** — `core/models/`: `Case`, `Hearing`, `Document`, `DocumentChunk`, `Conversation`, `Message`, `Citation`, `Folder`, `Email`, etc. All registered in `core/admin.py`.
- **AI services** — `core/services/`: `ai_service_factory.py` routes `get_llm_client()` / `get_embedding_service()` to `OllamaLLMClient`/`OllamaEmbeddingService` or the OpenAI equivalents based on `USE_OLLAMA`.
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
