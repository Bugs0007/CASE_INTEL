# Case Intel - Project Overview

**Last Updated:** March 2026
**Version:** 1.0.0

---

## Project Summary

| Attribute   | Value                                                      |
| ----------- | ---------------------------------------------------------- |
| **Name**    | Case Intel                                                 |
| **Type**    | Legal Case Management Platform                             |
| **Purpose** | AI-powered document search and Q&A for legal professionals |
| **Stack**   | Django + Next.js + PostgreSQL + LangGraph + Ollama/OpenAI  |

---

## Technology Stack

### Backend

| Component          | Technology            | Version | Purpose                             |
| ------------------ | --------------------- | ------- | ----------------------------------- |
| Framework          | Django                | 6.0.3   | Web framework                       |
| API                | Django REST Framework | 3.x     | REST API                            |
| Database           | PostgreSQL            | 15+     | Primary database                    |
| Vector DB          | pgvector              | 0.5+    | Vector similarity search            |
| AI Orchestration   | LangGraph             | latest  | AI workflow pipeline                |
| LLM (Local)        | Ollama                | latest  | Local LLM inference                 |
| LLM Model          | llama3.1:8b           | -       | Chat completions                    |
| Embeddings         | nomic-embed-text      | -       | 768-dim embeddings                  |
| LLM (Cloud)        | OpenAI                | -       | Alternative: gpt-4o                 |
| Embeddings (Cloud) | OpenAI                | -       | Alternative: text-embedding-3-small |

### Frontend

| Component   | Technology   | Version | Purpose                 |
| ----------- | ------------ | ------- | ----------------------- |
| Framework   | Next.js      | 15.x    | React framework         |
| Language    | TypeScript   | 5.x     | Type safety             |
| Styling     | Tailwind CSS | 3.x     | Utility-first CSS       |
| State       | React Query  | 5.x     | Server state management |
| Icons       | Lucide React | latest  | Icon library            |
| HTTP Client | Fetch API    | native  | API calls               |

---

## Directory Structure

### Backend (`/`)

| Path                             | Type | Description                |
| -------------------------------- | ---- | -------------------------- |
| `case_intel_project/`            | dir  | Django project settings    |
| `case_intel_project/settings.py` | file | Main configuration         |
| `case_intel_project/urls.py`     | file | Root URL routing           |
| `core/`                          | dir  | Main Django app            |
| `core/models/`                   | dir  | Database models (17 files) |
| `core/views/`                    | dir  | API views (7 files)        |
| `core/serializers/`              | dir  | DRF serializers (5 files)  |
| `core/services/`                 | dir  | Business logic (12 files)  |
| `core/admin.py`                  | file | Django admin config        |
| `core/urls.py`                   | file | API URL routing            |
| `media/documents/`               | dir  | Uploaded documents storage |
| `documentations/`                | dir  | Project documentation      |
| `scripts/`                       | dir  | Utility scripts            |

### Frontend (`frontend-next/`)

| Path                         | Type | Description                 |
| ---------------------------- | ---- | --------------------------- |
| `app/`                       | dir  | Next.js App Router pages    |
| `app/(dashboard)/`           | dir  | Dashboard route group       |
| `app/(dashboard)/page.tsx`   | file | Dashboard page              |
| `app/(dashboard)/cases/`     | dir  | Cases pages                 |
| `app/(dashboard)/documents/` | dir  | Documents page              |
| `app/(dashboard)/emails/`    | dir  | Emails page                 |
| `components/`                | dir  | React components            |
| `components/ui/`             | dir  | Base UI components          |
| `components/layout/`         | dir  | Layout components           |
| `components/dashboard/`      | dir  | Dashboard components        |
| `components/cases/`          | dir  | Case components             |
| `components/documents/`      | dir  | Document components         |
| `components/hearings/`       | dir  | Hearing components          |
| `components/emails/`         | dir  | Email components            |
| `components/chat/`           | dir  | Chat components             |
| `hooks/`                     | dir  | Custom React hooks          |
| `lib/`                       | dir  | Utilities and API client    |
| `types/`                     | dir  | TypeScript type definitions |
| `providers/`                 | dir  | React context providers     |

---

## Models Summary

| Model           | Table Name          | Fields | Relationships                                                       | Purpose                     |
| --------------- | ------------------- | ------ | ------------------------------------------------------------------- | --------------------------- |
| Case            | `cases`             | 11     | Has many: Hearing, Document, Email, Conversation, Task, ActivityLog | Core legal case entity      |
| Hearing         | `hearings`          | 10     | Belongs to: Case                                                    | Court hearing schedules     |
| Document        | `documents`         | 13     | Belongs to: Case, Folder; Has many: DocumentChunk                   | Uploaded legal documents    |
| DocumentChunk   | `document_chunks`   | 5      | Belongs to: Document                                                | Text chunks with embeddings |
| Conversation    | `conversations`     | 5      | Belongs to: Case; Has many: Message                                 | AI chat threads             |
| Message         | `messages`          | 5      | Belongs to: Conversation; Has many: Citation                        | Chat messages               |
| Citation        | `citations`         | 7      | Belongs to: Message, Document, Email, Chunk                         | AI answer sources           |
| Email           | `emails`            | 11     | Belongs to: Case; Has many: EmailAttachment                         | Synced Gmail messages       |
| EmailAttachment | `email_attachments` | 6      | Belongs to: Email, Document                                         | Email attachments           |
| GmailCredential | `gmail_credentials` | 8      | -                                                                   | OAuth tokens                |
| Task            | `tasks`             | 6      | Belongs to: Case                                                    | Case tasks                  |
| ActivityLog     | `activity_logs`     | 5      | Belongs to: Case                                                    | Audit trail                 |
| Folder          | `folders`           | 4      | Self-referential (parent)                                           | Document organization       |
| CaseTag         | `case_tags`         | 2      | Has many: CaseTagMap                                                | Tag definitions             |
| CaseTagMap      | `case_tag_map`      | 3      | Belongs to: Case, CaseTag                                           | Case-tag mapping            |
| DocumentTag     | `document_tags`     | 2      | Has many: DocumentTagMap                                            | Tag definitions             |
| DocumentTagMap  | `document_tag_map`  | 3      | Belongs to: Document, DocumentTag                                   | Document-tag mapping        |

---

## API Endpoints Summary

| Method | Endpoint                       | Description          | Auth |
| ------ | ------------------------------ | -------------------- | ---- |
| GET    | `/api/dashboard/`              | Dashboard statistics | No   |
| POST   | `/api/chat/`                   | AI Q&A processing    | No   |
| GET    | `/api/cases/`                  | List cases           | No   |
| POST   | `/api/cases/`                  | Create case          | No   |
| GET    | `/api/cases/{id}/`             | Get case             | No   |
| PATCH  | `/api/cases/{id}/`             | Update case          | No   |
| DELETE | `/api/cases/{id}/`             | Delete case          | No   |
| GET    | `/api/hearings/`               | List hearings        | No   |
| POST   | `/api/hearings/`               | Create hearing       | No   |
| GET    | `/api/hearings/{id}/`          | Get hearing          | No   |
| PATCH  | `/api/hearings/{id}/`          | Update hearing       | No   |
| DELETE | `/api/hearings/{id}/`          | Delete hearing       | No   |
| GET    | `/api/documents/`              | List documents       | No   |
| GET    | `/api/documents/{id}/`         | Get document         | No   |
| DELETE | `/api/documents/{id}/`         | Delete document      | No   |
| POST   | `/api/documents/upload/`       | Upload document      | No   |
| POST   | `/api/documents/{id}/process/` | Process document     | No   |
| GET    | `/api/conversations/`          | List conversations   | No   |
| GET    | `/api/conversations/{id}/`     | Get conversation     | No   |
| DELETE | `/api/conversations/{id}/`     | Delete conversation  | No   |
| GET    | `/api/gmail/auth/`             | Start OAuth flow     | No   |
| GET    | `/api/gmail/callback/`         | OAuth callback       | No   |
| GET    | `/api/gmail/status/`           | Connection status    | No   |
| POST   | `/api/gmail/sync/`             | Sync emails          | No   |
| GET    | `/api/emails/`                 | List emails          | No   |
| POST   | `/api/emails/{id}/link/`       | Link to case         | No   |

**Total Endpoints:** 26

---

## Services Architecture

| Service            | File                          | Purpose                          | Dependencies          |
| ------------------ | ----------------------------- | -------------------------------- | --------------------- |
| AI Service Factory | `ai_service_factory.py`       | Routes to Ollama or OpenAI       | settings              |
| Ollama LLM Client  | `ollama_llm_client.py`        | Chat completions via Ollama      | ollama                |
| Ollama Embedding   | `ollama_embedding_service.py` | Generate embeddings              | ollama                |
| LLM Client         | `llm_client.py`               | Chat completions via OpenAI      | openai                |
| Embedding Service  | `embedding_service.py`        | Generate embeddings via OpenAI   | openai                |
| Document Processor | `document_processor.py`       | Extract text, chunk, embed       | AI Factory            |
| Vector Search      | `vector_search_service.py`    | Semantic similarity search       | AI Factory, pgvector  |
| AI Workflow        | `ai_workflow.py`              | LangGraph pipeline orchestration | LangGraph, AI Factory |
| Gmail Service      | `gmail_service.py`            | Gmail API integration            | google-auth           |

---

## LangGraph Pipeline

| Node                    | Input                    | Output              | Purpose                  |
| ----------------------- | ------------------------ | ------------------- | ------------------------ |
| `route_query`           | query, case_id           | query_type, filters | Classify and route query |
| `analyze_query`         | query                    | entities, intent    | Extract query components |
| `vector_search`         | query_embedding, filters | chunks[]            | Find relevant chunks     |
| `rank_chunks`           | chunks[], query          | ranked_chunks[]     | Re-rank by relevance     |
| `generate_answer`       | query, context           | answer, confidence  | Generate response        |
| `extract_citations`     | answer, chunks           | citations[]         | Identify sources         |
| `format_response`       | answer, citations        | final_response      | Format final output      |
| `handle_no_results`     | -                        | fallback_response   | Handle empty results     |
| `handle_low_confidence` | -                        | clarification       | Handle low confidence    |

**Flow Diagram:**

```
route_query → analyze_query → vector_search
                                    │
                              ┌─────┼─────┐
                              │     │     │
                              ▼     ▼     ▼
                         no_results │  low_conf
                              │     │     │
                              │     ▼     │
                              │ rank_chunks
                              │     │     │
                              │     ▼     │
                              │ generate  │
                              │     │     │
                              │     ▼     │
                              │ citations │
                              │     │     │
                              └─────┼─────┘
                                    ▼
                             format_response
```

---

## Frontend Pages

| Route         | Page        | Components                                              | Data Source                             |
| ------------- | ----------- | ------------------------------------------------------- | --------------------------------------- |
| `/`           | Dashboard   | StatCards, RecentActivity, ActiveCases, QuickActions    | `GET /dashboard/`                       |
| `/cases`      | Cases List  | CaseFilters, CaseGrid, CaseCard                         | `GET /cases/`                           |
| `/cases/[id]` | Case Detail | CaseDetailHeader, CaseOverview, HearingsList, ChatPanel | `GET /cases/{id}/`, hearings, documents |
| `/documents`  | Documents   | DocumentFilters, DocumentTable                          | `GET /documents/`                       |
| `/emails`     | Emails      | GmailStatus, SyncConfig, EmailsTable                    | `GET /gmail/status/`, `GET /emails/`    |

---

## Configuration

### Environment Variables

| Variable                 | Required            | Default                | Description                               |
| ------------------------ | ------------------- | ---------------------- | ----------------------------------------- |
| `DB_NAME`                | Yes                 | -                      | PostgreSQL database name                  |
| `DB_USER`                | Yes                 | -                      | Database username                         |
| `DB_PASSWORD`            | Yes                 | -                      | Database password                         |
| `DB_HOST`                | No                  | localhost              | Database host                             |
| `DB_PORT`                | No                  | 5432                   | Database port                             |
| `USE_OLLAMA`             | No                  | true                   | Use local Ollama (true) or OpenAI (false) |
| `OLLAMA_BASE_URL`        | No                  | http://localhost:11434 | Ollama server URL                         |
| `OLLAMA_MODEL`           | No                  | llama3.1:8b            | Ollama chat model                         |
| `OLLAMA_EMBEDDING_MODEL` | No                  | nomic-embed-text       | Ollama embedding model                    |
| `OPENAI_API_KEY`         | If USE_OLLAMA=false | -                      | OpenAI API key                            |
| `OPENAI_MODEL`           | No                  | gpt-4o                 | OpenAI chat model                         |
| `OPENAI_EMBEDDING_MODEL` | No                  | text-embedding-3-small | OpenAI embedding model                    |
| `GOOGLE_CLIENT_ID`       | For Gmail           | -                      | Google OAuth client ID                    |
| `GOOGLE_CLIENT_SECRET`   | For Gmail           | -                      | Google OAuth client secret                |
| `GOOGLE_REDIRECT_URI`    | For Gmail           | -                      | OAuth callback URL                        |

---

## Dependencies

### Backend (requirements.txt)

| Package                  | Version | Purpose            |
| ------------------------ | ------- | ------------------ |
| django                   | 6.0.3   | Web framework      |
| djangorestframework      | 3.x     | REST API           |
| psycopg2-binary          | latest  | PostgreSQL driver  |
| pgvector                 | latest  | Vector extension   |
| langgraph                | latest  | AI workflow        |
| ollama                   | latest  | Ollama client      |
| langchain-ollama         | latest  | LangChain Ollama   |
| openai                   | latest  | OpenAI client      |
| google-auth              | latest  | Google OAuth       |
| google-api-python-client | latest  | Gmail API          |
| python-dotenv            | latest  | Environment config |
| PyPDF2                   | latest  | PDF parsing        |
| python-docx              | latest  | DOCX parsing       |

### Frontend (package.json)

| Package               | Version | Purpose         |
| --------------------- | ------- | --------------- |
| react                 | 19.x    | UI library      |
| next                  | 15.x    | React framework |
| typescript            | 5.x     | Type safety     |
| tailwindcss           | 3.x     | CSS framework   |
| @tanstack/react-query | 5.x     | Data fetching   |
| lucide-react          | latest  | Icons           |
| clsx                  | latest  | Class utilities |
| tailwind-merge        | latest  | Class merging   |

---

## Startup Commands

### Development

| Service    | Command                               | Port  |
| ---------- | ------------------------------------- | ----- |
| PostgreSQL | `docker run -p 5432:5432 postgres:15` | 5432  |
| Ollama     | `ollama serve`                        | 11434 |
| Django     | `python manage.py runserver`          | 8000  |
| Next.js    | `cd frontend-next && npm run dev`     | 3000  |

### Production

| Service | Command                                        |
| ------- | ---------------------------------------------- |
| Django  | `gunicorn case_intel_project.wsgi:application` |
| Next.js | `npm run build && npm start`                   |

---

## File Counts

| Category         | Count |
| ---------------- | ----- |
| Django Models    | 17    |
| API Views        | 7     |
| Serializers      | 5     |
| Services         | 12    |
| React Components | 35+   |
| Custom Hooks     | 8     |
| TypeScript Types | 6     |
| API Endpoints    | 26    |
| Database Tables  | 17    |

---

## Feature Matrix

| Feature             | Backend            | Frontend             | Status   |
| ------------------- | ------------------ | -------------------- | -------- |
| Case Management     | CRUD API           | List, Detail, Create | Complete |
| Hearing Management  | CRUD API           | List, CRUD UI        | Complete |
| Document Upload     | Upload endpoint    | Upload dialog        | Complete |
| Document Processing | Process endpoint   | Process button       | Complete |
| Vector Search       | pgvector queries   | -                    | Complete |
| AI Q&A              | LangGraph pipeline | Chat panel           | Complete |
| Citations           | Auto-extraction    | Display in chat      | Complete |
| Gmail OAuth         | OAuth flow         | Connect UI           | Complete |
| Email Sync          | Sync endpoint      | Sync config          | Complete |
| Email Linking       | Link endpoint      | Link button          | Complete |
| Dashboard Stats     | Aggregation API    | Stat cards           | Complete |
| Activity Feed       | ActivityLog model  | Recent activity      | Complete |

---

## Testing

| Type           | Location                     | Framework                    |
| -------------- | ---------------------------- | ---------------------------- |
| Backend Unit   | `tests/`                     | pytest                       |
| API Tests      | `tests/test_api.py`          | Django test client           |
| AI Integration | `test_ollama_integration.py` | pytest                       |
| Frontend       | Not yet                      | Jest + React Testing Library |

---

## Documentation Files

| File                  | Description                  |
| --------------------- | ---------------------------- |
| `README.md`           | Project overview and setup   |
| `QUICKSTART.md`       | 3-minute setup guide         |
| `ARCHITECTURE.md`     | System architecture          |
| `SYSTEM_DESIGN.md`    | Design documentation         |
| `DB_SCHEMA.md`        | Database schema reference    |
| `API_CONTRACTS.md`    | API endpoint documentation   |
| `PROJECT_OVERVIEW.md` | This file - tabular overview |
| `OLLAMA_SETUP.md`     | Ollama configuration guide   |
| `NAVIGATION.md`       | Codebase navigation guide    |
