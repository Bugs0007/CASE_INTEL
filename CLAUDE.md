# Case Intel
Legal case management platform for Indian advocates. Django/DRF backend,
Next.js 15 / React 19 / TypeScript / Tailwind frontend (`frontend-next/`),
PostgreSQL with pgvector on RDS. Deployed on EC2 (Nginx + gunicorn + systemd).
Live at caseintel.duckdns.org.

## Architecture
- Django project lives at the **repo root**, not a `backend/` subfolder —
  `manage.py` and `case_intel_project/` (settings, urls, celery, asgi/wsgi)
  are top-level, sibling to `frontend-next/`. Django 5.1.11 is pinned (do not
  upgrade — conflicts with `django-celery-beat` as installed here; ignore the
  README badge, which incorrectly says 6.0.3).
- This is a **single-app project**: everything lives in `core/` — cases,
  hearings, documents/chunks/embeddings, conversations, chat (LangGraph),
  folders, Gmail sync, and eCourts case tracking. Other `INSTALLED_APPS` are
  off-the-shelf: DRF + `rest_framework.authtoken` (token auth), `corsheaders`,
  `django_extensions`, `storages` (S3). `django_celery_beat`/
  `django_celery_results` are installed for their admin/models only — Celery
  itself is **not wired up** (no broker configured, no real task dispatch
  anywhere); background work instead runs through `manage.py process_jobs`
  polling a Postgres-backed `ProcessingJob` queue.
- eCourts scraper: `core/services/court_data/` (`base.py` provider interface,
  `ecourts_provider.py` the actual `bharat-courts`-backed implementation,
  `models.py`, `exceptions.py`), plus `core/services/court_tracking.py`
  (rate-limited refresh/preview/confirm service) and
  `core/services/court_order_sync.py` (order PDF download). CAPTCHA-gated —
  treat every fetch as expensive and cacheable. In practice: CAPTCHA is
  solved automatically via OCR (`ddddocr`, ~75% accuracy) with its own retry
  loop, every fetch opens a fresh session (eCourts has no login and
  download links are session-bound, so nothing is reusable across fetches),
  and cost is controlled via rate limiting rather than caching — at most one
  real portal fetch per case per hour (`MIN_REFETCH_INTERVAL`), with cached
  results served from `CourtFetchLog` snapshots in between. Only the
  near-static court hierarchy (states/districts/benches) is cached (Redis,
  30-day TTL) — case status/orders are always a live hit when a fetch
  actually happens.
- RAG pipeline: `core/services/graph/` (`state.py`, `nodes.py`,
  `builder.py`, `config.py`). Flow: `hyde_expand → hybrid_search →
  generate_answer → END` (simplified from an earlier 9-node graph — see
  `builder.py` docstring). Currently supports general multi-document Q&A
  chat scoped by `case_id`: spaCy-based chunking (`document_processor.py`,
  500-char chunks/100-char overlap), pluggable embeddings (Gemini/Ollama/
  OpenAI via `ai_service_factory.py`, DB column fixed at 768-dim regardless
  of provider), hybrid retrieval (pgvector cosine + Postgres full-text, RRF
  fusion) plus a local cross-encoder reranker, all in
  `vector_search_service.py`. **Note:** as of this codebase, there is no
  summarization-specific code path yet — `query_type="summarize"` is just a
  UI label that doesn't branch retrieval or generation logic. It is being
  REPURPOSED for single-order-PDF summarization only — do not extend
  the general document-chat feature.
- Order PDFs are named `{CNR}_order_{seq}_{YYYY-MM-DD}.pdf` (confirmed exact
  match in `core/services/court_order_sync.py`'s `_order_filename()`;
  unsafe characters replaced with `-`, stored under
  `documents/court_orders/`).
- Frontend: `frontend-next/` (Next.js 15, React 19, TypeScript, Tailwind; no
  heavy UI kit — `lucide-react` for icons, `@tanstack/react-query` for data
  fetching). Structure: `app/` (App Router — `login/`, `(dashboard)/` route
  group), `components/` (incl. `auth-guard.tsx`), `providers/`, `lib/`
  (`auth.ts` + `lib/api/` — one API client file per domain: cases, hearings,
  documents, chat, emails, gmail, case-tracking, dashboard), `hooks/`
  (React Query hooks per domain), `types/`. Auth: DRF `TokenAuthentication`
  — login POSTs to `/api/auth/login/`, token stored in `localStorage`
  (`case_intel_token`), sent as `Authorization: Token <token>` on every
  request via `lib/api/client.ts` (not `Bearer`/JWT); a 401 clears the token
  and redirects to `/login`; `auth-guard.tsx` gates the dashboard route
  group client-side. Backend URL comes from `NEXT_PUBLIC_API_URL`.

## Conventions
- Python: Django 5.x idioms, DRF ViewSets + serializers, no function-based views
- Every model that holds user data MUST have an owner FK and every queryset
  MUST filter by request.user (multi-tenant by row)
- Migrations: never edit an applied migration; always makemigrations fresh
- Tests: pytest-django, put tests next to the app in tests/ (NOT currently
  set up — no `pytest-django` in `requirements.txt` and no `tests/`
  directory exists under `core/` yet; introduce the dependency when adding
  the first test)
- Never touch: deployment configs, systemd units, nginx conf, GitHub Actions,
  .env files. Flag needed changes in your summary instead.
- Never run `git commit` or `git push` — leave changes uncommitted in the
  working tree for me to review and commit myself.

## Commands
- Run backend: `python manage.py runserver` (repo root, venv active) —
  migrate first with `python manage.py migrate`; no Makefile exists.
- Run frontend: `cd frontend-next && npm run dev`
- Run tests: pytest (see Conventions note — not wired up yet; the only
  currently-working test invocation is `python manage.py test core`, which
  exercises no real test suite as of this commit)
- Lint: `cd frontend-next && npm run lint` (`next lint` / `eslint-config-next`);
  no Python linter (flake8/ruff/black) is configured in this repo
