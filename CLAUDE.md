# Case Intel

Legal case management platform with AI-powered document search and Q&A over uploaded case documents.

## Stack

- **Backend:** Django 5.1.11 (pinned — see Gotchas) + Django REST Framework 3.17, `core` is the only app
- **DB:** PostgreSQL with `pgvector` (RDS in production)
- **AI:** LangGraph 0.6.11 pipeline via a factory pattern. LLM (chat generation) provider is independently configurable — Groq, Ollama, or OpenAI. Embedding provider is independently configurable too — Gemini (`gemini-embedding-001`, truncated to 768-dim via `output_dimensionality`), Ollama (`nomic-embed-text`, native 768-dim), or OpenAI as a fallback path.
- **Frontend:** `frontend-next/` — Next.js 15 / React 19 / TypeScript / Tailwind, deployed on Vercel
- **Async/cache:** Celery + Redis (`django_celery_beat`, `django_celery_results`)
- **Config:** `python-decouple`, all environment-dependent settings must be read via `config(...)` in `case_intel_project/settings.py` — never hardcode `DEBUG`, `ALLOWED_HOSTS`, `SECRET_KEY`, DB credentials, or API keys directly in source.

## Architecture

- **Models** — `core/models/`: `Case`, `Hearing`, `Document`, `DocumentChunk`, `Conversation`, `Message`, `Citation`, `Folder`, `Email`, etc. All registered in `core/admin.py`. All case-data-holding models inherit an `OwnedModel` abstract mixin (`owner` FK to `User`, `on_delete=PROTECT`) for multi-tenant row isolation — see Conventions below.
- **AI services** — `core/services/`: `ai_service_factory.py` has two independent toggle chains, one per axis. `get_llm_client()` checks `USE_GROQ` first (routes to `LLMClient` with Groq's OpenAI-compatible `base_url`), then `USE_OLLAMA` (`OllamaLLMClient`), then falls back to OpenAI (`LLMClient` with no `base_url` override) — untouched by `USE_GEMINI_EMBEDDINGS`. `get_embedding_service()` checks `USE_GEMINI_EMBEDDINGS` first (`GeminiEmbeddingService`), then `USE_OLLAMA` (`OllamaEmbeddingService`), then falls back to OpenAI's `EmbeddingService` — untouched by `USE_GROQ`. `GeminiEmbeddingService` always passes `output_dimensionality=settings.EMBEDDING_DIMENSIONS` (768) explicitly on every `embed_content` call and batches up to 100 texts per request (the API's per-request cap); it raises on any API error rather than falling back to another provider mid-document, since mixing embedding models within a document corrupts retrieval.
- **LangGraph pipeline** — `core/services/graph/` (`state.py`, `nodes.py`, `builder.py`). Current flow (lean 3-node, rewritten from an earlier 9-node version — see `builder.py` docstring for the rationale, ~8-12s latency, 2 LLM calls/query):

  ```
  hyde_expand → hybrid_search → generate_answer → END
  ```

  **This pipeline is being repurposed for single-order-PDF summarization only, per the current roadmap — do not extend it into a general multi-document chat feature.** See `/areas/case-intel` planning notes for the Order Overview feature spec when that work starts.

- **Background processing** — document processing (extract → OCR if scanned → chunk → embed) is **asynchronous**: upload/process endpoints only enqueue a `ProcessingJob` row and return; the `manage.py process_jobs` worker (systemd unit `case-intel-worker` in production, see `deploy/case-intel-worker.service`) claims jobs via `select_for_update(skip_locked=True)` — Postgres **is** the queue, deliberately no Redis/Celery. Progress is written to the job row per chunk-batch and surfaced through `DocumentSerializer`. Scanned PDFs (negligible extractable text) are OCRed with `ocrmypdf --skip-text` in 10-page batches inside the worker (`core/services/ocr_service.py`), setting `Document.ocr_applied`.
- **Views/serializers** — `core/views/`, `core/serializers/`, both modular packages split by domain (chat, case, conversation, document, hearing, gmail, email, folder, dashboard).
- **URLs** — `core/urls.py`, all endpoints mounted under `/api/`.
- **Multi-tenancy** — `core/views/mixins.py`'s `OwnerScopedMixin` is applied to every generic view; it filters `get_queryset()` by `request.user` and stamps `owner` on create, which also covers object-level retrieve/update/delete since DRF's `get_object()` reuses `get_queryset()`. Plain `APIView`s (dashboard, chat, gmail, case_tracking, document upload/process/download) are scoped manually — check each one individually rather than assuming the mixin covers it. Serializers with writable FKs to owned objects (`Hearing.case`, `Document.folder`, `Folder.parent_folder`) scope those PK querysets to the caller's own rows too.
- **Auth** — DRF `TokenAuthentication`. Frontend sends `Authorization: Token <token>`, stored in `localStorage`. Chosen over session/JWT because Vercel↔EC2 is cross-origin with `CORS_ALLOW_CREDENTIALS=False`, so cookies don't work here regardless.

## API Endpoints (all under `/api/`)

`dashboard/`, `chat/`, `conversations/`, `conversations/<id>/`, `conversations/<id>/messages/`, `conversations/<id>/export/`, `cases/`, `cases/<id>/`, `hearings/`, `hearings/<id>/`, `documents/`, `documents/<id>/`, `documents/upload/`, `documents/<id>/process/`, `folders/`, `gmail/auth/`, `gmail/callback/`, `gmail/status/`, `gmail/sync/`, `emails/`, `emails/<id>/link/`, `auth/register/`, `auth/login/`, `auth/logout/`

Note: `gmail/callback/` is hit directly by Google's OAuth redirect (not a token-authenticated frontend call), and remains intentionally `AllowAny` along with `auth/login/` — keep that in mind if endpoint auth requirements change.

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
python -m spacy download en_core_web_sm   # required once after every fresh pip install — see Gotchas
pytest                               # test suite now exists — see Testing below

# Frontend (from frontend-next/)
npm install                          # ALWAYS run this before build/lint, even if
                                      # node_modules appears to exist — it does not
                                      # persist across fresh checkouts/worktrees/containers
npm run dev
npm run build
npm run lint
```

## Testing

`pytest` + `pytest-django` (`pytest.ini` at repo root). `core/tests/test_multi_tenancy.py` covers cross-user isolation on Case/Hearing/Document/Conversation export and the register/login/logout flow. This is new as of the multi-tenancy work — extend it as new owned models/endpoints are added, don't let it stay a one-off.

**Frontend verification is not optional when `frontend-next/` files change.** Run `npm install && npm run build && npm run lint` from `frontend-next/` and actually read the output — don't report a task as tested if this step was skipped because `node_modules` was missing.

## Workflow conventions for AI-assisted changes (Claude Code)

- **Never run `git commit` or `git push`.** Leave changes uncommitted in the working tree for manual review and commit.
- **Never touch deployment configs**: systemd units, nginx conf, GitHub Actions, `.env` files. Flag needed changes in your summary instead.
- **Every model holding user/case data must have an `owner` FK** (via `OwnedModel`) and **every queryset must filter by `request.user`** — either through `OwnerScopedMixin` or manual scoping on plain `APIView`s. Check writable serializer FKs too (see Multi-tenancy above) — an unscoped PK field is an IDOR path even if the view itself is scoped.
- **Migrations**: never edit an applied migration; always `makemigrations` fresh. For migrations adding a NOT NULL column to a table with real production rows, use the `CHECK ... NOT VALID → VALIDATE → SET NOT NULL` pattern and `CREATE INDEX CONCURRENTLY` rather than a bare apply, to avoid an `ACCESS EXCLUSIVE` lock on RDS during business hours.
- **Django is pinned to 5.1.11 — do not upgrade it** (see Gotchas) as part of unrelated work; if a task seems to require a newer Django, stop and flag it rather than bumping the pin.

## Gotchas

- **Django is pinned to 5.1.11** — do not upgrade. A newer Django version conflicts with `django-celery-beat` as installed here. Check `requirements.txt` compatibility before ever touching this pin.
- **`DEBUG` / `ALLOWED_HOSTS` / `SECRET_KEY` must come from `.env` via `python-decouple`**, not be hardcoded. (`SECRET_KEY` was hardcoded in source until this was fixed — if you see a hardcoded fallback default in `settings.py`, that's intentional for local-dev-without-`.env` convenience, not a place to put real secrets.)
- **Embedding dimensions are NOT fully dynamic.** `settings.py` computes `EMBEDDING_DIMENSIONS` dynamically based on `USE_GEMINI_EMBEDDINGS` / `USE_OLLAMA` + the configured model (768 hardcoded for Gemini regardless of `GEMINI_EMBEDDING_MODEL`'s native dimension, 768 for Ollama `nomic-embed-text`, 1536 for OpenAI `text-embedding-3-small`), but `core/models/document_chunk.py`'s `DocumentChunk.embedding` field is **hardcoded** to `VectorField(dimensions=768)`. If you switch to OpenAI's embedder (1536-dim, no `output_dimensionality` truncation applied), embedding writes will fail or silently mismatch against the fixed 768-dim column/HNSW index. A real migration (changing the field + re-embedding existing chunks) is required to actually switch to a non-768 provider in a running deployment — flipping the env var alone is not sufficient. Gemini and Ollama are both safe to switch between since both are pinned to 768 already.
- **CORS/auth are different domains** — Vercel frontend and EC2 backend are cross-origin. Token-based auth (see Multi-tenancy above) is what's actually implemented, specifically to sidestep cross-domain cookie issues.
- `.env` is gitignored and has never been committed — keep it that way. Never put real secrets directly into `settings.py` defaults.
- **`USE_GROQ` only affects chat generation, never embeddings; `USE_GEMINI_EMBEDDINGS` only affects embeddings, never generation.** These two toggles are fully decoupled axes. If both are false, embeddings fall through to Ollama's `nomic-embed-text` — Ollama must still be installed and running in that case regardless of `USE_GROQ`.
- **No production `GROQ_API_KEY` or `GEMINI_API_KEY` exists yet.** Keys used to verify these integrations were local-testing-only. Before `USE_GROQ=true` or `USE_GEMINI_EMBEDDINGS=true` can go live, generate dedicated production keys (console.groq.com/keys, aistudio.google.com/apikey) and add them to prod `.env` — do not reuse dev/test keys for production. Also see the Ollama-on-EC2 gap noted for the same deploy (Ollama isn't installed on the EC2 instance yet, and is still the embedding fallback if `USE_GEMINI_EMBEDDINGS=false`).
- **`GeminiEmbeddingService` never silently falls back to Ollama/OpenAI on failure.** A Gemini rate limit, network error, or bad API key fails the whole `DocumentProcessor.process_document()` job (caught by its top-level `except Exception` → `processing_status="failed"` → re-raise) rather than completing the document with a mix of Gemini- and Ollama-sourced vectors, which would silently corrupt retrieval since the two models' vector spaces aren't comparable.
- **OCR needs system binaries, not just pip.** `ocrmypdf` (in `requirements.txt`) requires `tesseract-ocr` and `ghostscript` installed as system packages — both are in `deploy/provision.sh`'s apt list, but a machine that only ran `pip install -r requirements.txt` cannot OCR (the worker will fail those jobs with a subprocess error). On Windows dev boxes install Tesseract (UB-Mannheim build) and Ghostscript and put both on PATH.
- **Documents don't process unless the worker is running.** Uploading only enqueues a `ProcessingJob`; run `python manage.py process_jobs` locally (or ensure the `case-intel-worker` systemd service is up in production) or every document sits at "queued" forever.
- **`spacy` in `requirements.txt` does NOT include its language model.** `core/services/document_processor.py`'s `_get_nlp()` loads `en_core_web_sm` for sentence splitting, but spaCy models aren't distributed as regular pip packages — `pip install -r requirements.txt` alone will not fetch it. Run `python -m spacy download en_core_web_sm` once after every fresh install (local, CI, or EC2). If skipped, this doesn't hard-crash — `_get_nlp()` catches the `OSError` and silently falls back to a blank spaCy sentencizer (worse sentence boundaries, no linguistic features), so the gap can go unnoticed for a while. `.claude/commands/deploy-checks.md` documents this as a required post-`pip install` step.
- **`node_modules` in `frontend-next/` is gitignored and does not persist across fresh checkouts, containers, or `git worktree`s.** If frontend build/lint wasn't run on a given task, check this first before assuming it was skipped for another reason — see Testing above.
