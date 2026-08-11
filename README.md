# Case Intel

Legal case management platform for a solo/small-firm advocate practicing in Indian courts.

## What it does

- **Case tracking against live eCourts data** — enter a CNR or a case number/court/year, and Case Intel fetches case status, hearing history, and orders directly from `services.ecourts.gov.in` (District Courts) or `hcservices.ecourts.gov.in` (High Courts), then keeps them refreshed.
- **Advocate search** — search an advocate by name or bar code across every district/court complex in a state at once, and bulk-import the matching cases.
- **Document management with AI order summaries** — upload case documents; court orders are automatically summarized (what happened, directions for each party, next hearing date) by an LLM, with cheap non-LLM paths for unreadable/routine/short orders.
- **"Case Bot"** — a general-purpose AI chat over a case's uploaded documents (retrieval-augmented, with citations), separate from the order-summary feature above.
- **Cause lists** — Telangana High Court daily cause-list PDFs, fetched and parsed automatically.
- **Appearance-fee invoicing** — record a fee, generate a PDF invoice, email it to the client's billing contact, track paid/unpaid.
- **Travel booking, hearing scheduling, Gmail sync** for case-related correspondence.

Everything is scoped per advocate (multi-tenant, token-authenticated) — see [CLAUDE.md](CLAUDE.md) for the full architecture reference.

## Stack

| Layer          | Technology                                                    |
| -------------- | --------------------------------------------------------------|
| Backend        | Django 5.1.11 + Django REST Framework                         |
| Database       | PostgreSQL + `pgvector`                                       |
| AI (chat)      | LangGraph — hybrid pgvector/keyword retrieval + LLM generation|
| AI (summaries) | Direct LLM call, no retrieval — see CLAUDE.md                 |
| LLM providers  | Groq, Ollama, or OpenAI (switchable independently of embeddings) |
| Embeddings     | Gemini, Ollama, or OpenAI (switchable independently of the LLM)  |
| Court data     | `bharat-courts` against the live eCourts portals               |
| Frontend       | Next.js 15, React 19, TypeScript, Tailwind CSS                 |
| Background jobs| Postgres-backed queue (`ProcessingJob` + `manage.py process_jobs`) — no Celery/Redis |

## Prerequisites

- Python 3.11+ (the pinned `ddddocr`/`opencv-python-headless` versions target 3.13; anything 3.11+ works)
- Node.js 18+
- PostgreSQL 15+ with the [pgvector](https://github.com/pgvector/pgvector) extension
- Tesseract OCR + Ghostscript (needed by `ocrmypdf` for scanned documents — see Gotchas in CLAUDE.md for platform-specific install notes)
- At least one LLM provider reachable: [Ollama](https://ollama.ai) running locally, or a Groq/OpenAI API key
- At least one embedding provider reachable: Ollama, or a Gemini/OpenAI API key

## Setup

### 1. Backend

```bash
git clone <repo-url>
cd CASE_INTEL

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python -m spacy download en_core_web_sm   # required — see Gotchas in CLAUDE.md

cp .env.example .env
# edit .env — see Environment variables below
```

### 2. Database

```bash
psql -U postgres -c "CREATE DATABASE case_intel;"
psql -U postgres -d case_intel -c "CREATE EXTENSION vector;"

python manage.py migrate
python manage.py createsuperuser
```

### 3. AI provider

Pick one LLM provider and one embedding provider (they're independent — see [CLAUDE.md](CLAUDE.md#stack)):

```bash
# Ollama (local, free, covers both axes)
ollama pull llama3.1:8b
ollama pull nomic-embed-text
ollama serve

# OR set in .env: USE_GROQ=true + GROQ_API_KEY=... (LLM)
# OR set in .env: USE_GEMINI_EMBEDDINGS=true + GEMINI_API_KEY=... (embeddings)
```

### 4. Run it

```bash
# Terminal 1 — backend
python manage.py runserver

# Terminal 2 — background worker (required: uploads/order summaries/advocate
# search/cause lists all sit "queued" forever without this running)
python manage.py process_jobs

# Terminal 3 — frontend
cd frontend-next
npm install   # always run this even if node_modules exists — see CLAUDE.md
npm run dev
```

- Backend API: http://localhost:8000/api/
- Frontend: http://localhost:3000

## Environment variables

`.env.example` documents every variable settings.py reads, with defaults where they exist. The ones actually required to get a working local instance:

| Variable | Required? | Notes |
| --- | --- | --- |
| `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` | Yes | `SECRET_KEY` has an insecure fallback in `settings.py` for local dev only — never rely on it in production |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Yes | |
| One of: `USE_OLLAMA=true`, or `USE_GROQ=true` + `GROQ_API_KEY` | Yes | LLM (chat generation) provider |
| One of: Ollama running, or `USE_GEMINI_EMBEDDINGS=true` + `GEMINI_API_KEY` | Yes | Embedding provider — independent toggle from the LLM one |
| `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET` | Only for Gmail sync | Everything else works without it |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | Only for invoice email delivery | **Not set anywhere yet, including production.** Without these, invoice "send" logs the delivery instead of emailing it — the feature stays usable, just without real email. |
| `USE_S3` + `AWS_*` | Only for S3 storage | Defaults to local disk under `media/` |
| `TELANGANA_HC_COURT_KEY`, `TELANGANA_HC_BENCH_CODE` | No | Defaults work as-is |

See [CLAUDE.md](CLAUDE.md) for exactly how the LLM/embedding provider toggle chains resolve, and the 768-dim embedding column gotcha if you ever change providers on a running deployment with existing data.

## Testing

```bash
pytest                                        # ~340 tests, pytest-django (pytest.ini at repo root)

cd frontend-next
npm install && npm run build && npm run lint  # required whenever frontend-next/ files change
```

## Deployment

Production runs on a single EC2 instance behind Nginx (gunicorn + a separate `process_jobs` systemd worker), with RDS Postgres and Vercel for the frontend.

- **First-time provisioning** (fresh AWS account → live app): [PROVISIONING.md](PROVISIONING.md) — mostly automated by `deploy/provision.sh`, with the genuinely manual steps (RDS creation, DNS, TLS cert, GitHub Actions secrets) called out explicitly.
- **Ongoing deploys**: push to `main` triggers [.github/workflows/deploy.yml](.github/workflows/deploy.yml) — pulls, migrates, `collectstatic`, restarts both the web and worker systemd units. Assumes provisioning already happened.
- **Cron**: `manage.py fetch_cause_lists` has no scheduler wired into any deploy config — there's deliberately no Celery/Redis in this project. An operator needs to add two lines to the box's crontab (or an equivalent pair of systemd timers):

  ```cron
  0 19 * * *   cd /home/ubuntu/CASE_INTEL && .venv/bin/python manage.py fetch_cause_lists   # evening before
  30 6 * * *   cd /home/ubuntu/CASE_INTEL && .venv/bin/python manage.py fetch_cause_lists   # morning of
  ```

  Two runs a day is intentional, not redundant — a missed evening run is fully repaired by the next morning's.

## Documentation

- [CLAUDE.md](CLAUDE.md) — architecture, conventions, and gotchas (the canonical reference — kept current, everything else here is a summary of it)
- [PROVISIONING.md](PROVISIONING.md) — full server provisioning walkthrough
- [documentations/05-future-scope/](documentations/05-future-scope/) — forward-looking design notes for unimplemented features
