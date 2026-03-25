<p align="center">
  <img src="https://img.shields.io/badge/Django-6.0.3-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django"/>
  <img src="https://img.shields.io/badge/Next.js-15-000000?style=for-the-badge&logo=nextdotjs&logoColor=white" alt="Next.js"/>
  <img src="https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL"/>
  <img src="https://img.shields.io/badge/LangGraph-AI-FF6B6B?style=for-the-badge&logo=langchain&logoColor=white" alt="LangGraph"/>
  <img src="https://img.shields.io/badge/Ollama-Local_AI-000000?style=for-the-badge&logo=ollama&logoColor=white" alt="Ollama"/>
</p>

<p align="center">
  <a href="https://github.com/Bugs0007/CASE_INTEL/stargazers"><img src="https://img.shields.io/github/stars/Bugs0007/CASE_INTEL?style=social" alt="Stars"/></a>
  <a href="https://github.com/Bugs0007/CASE_INTEL/network/members"><img src="https://img.shields.io/github/forks/Bugs0007/CASE_INTEL?style=social" alt="Forks"/></a>
  <a href="https://github.com/Bugs0007/CASE_INTEL"><img src="https://img.shields.io/github/last-commit/Bugs0007/CASE_INTEL" alt="Last Commit"/></a>
</p>

<h1 align="center">Case Intel</h1>

<p align="center">
  <strong>AI-Powered Legal Case Management Platform</strong><br>
  <em>Semantic document search, intelligent Q&A, and case organization for legal professionals</em>
</p>

<p align="center">
  <a href="#-features">Features</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-api-reference">API</a> •
  <a href="#-contributing">Contributing</a>
</p>

---

## Why Case Intel?

Legal professionals spend **60% of their time** searching through documents. Case Intel changes that.

- **Ask questions in plain English** — Get instant answers with source citations
- **Semantic search** — Find relevant content even if keywords don't match
- **100% private** — Run entirely locally with Ollama, or use OpenAI for cloud power
- **Modern stack** — Django + Next.js + LangGraph for reliability and extensibility

---

## Features

### Document Intelligence

- **Upload & Process** — PDF, DOCX, TXT support with automatic text extraction
- **Smart Chunking** — Semantic segmentation preserves context
- **Vector Embeddings** — 768-dim (Ollama) or 1536-dim (OpenAI) embeddings via pgvector

### AI-Powered Q&A

- **Natural Language Queries** — "What were the key arguments in the motion?"
- **Source Citations** — Every answer links back to source documents
- **Confidence Scores** — Know how reliable each answer is
- **Conversation History** — Continue discussions across sessions

### Case Management

- **Organize Cases** — Track case number, parties, status, priority
- **Hearing Scheduler** — Manage upcoming and past court dates
- **Document Folders** — Hierarchical organization
- **Gmail Integration** — Sync case-related emails (OAuth)

### Flexible AI Backend

```
┌─────────────────────────────────────────────────────┐
│          Single ENV variable switches AI            │
│                                                     │
│   USE_OLLAMA=true          USE_OLLAMA=false        │
│   ┌─────────────────┐      ┌─────────────────┐     │
│   │  Ollama Local   │      │  OpenAI Cloud   │     │
│   │  llama3.1:8b    │      │  gpt-4o         │     │
│   │  nomic-embed    │      │  text-embed-3   │     │
│   │  Zero API cost  │      │  Superior perf  │     │
│   │  Full privacy   │      │  Easy setup     │     │
│   └─────────────────┘      └─────────────────┘     │
└─────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+ (for frontend)
- PostgreSQL 15+ with [pgvector](https://github.com/pgvector/pgvector) extension
- [Ollama](https://ollama.ai) (recommended) OR OpenAI API key

### 1. Clone & Setup Backend

```bash
git clone https://github.com/Bugs0007/CASE_INTEL.git
cd CASE_INTEL

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your database credentials
```

### 2. Setup Database

```bash
# Create PostgreSQL database with pgvector
psql -U postgres -c "CREATE DATABASE case_intel;"
psql -U postgres -d case_intel -c "CREATE EXTENSION vector;"

# Run migrations
python manage.py migrate
```

### 3. Setup AI (Choose One)

**Option A: Ollama (Recommended — Free & Private)**

```bash
# Install Ollama from https://ollama.ai
ollama pull llama3.1:8b
ollama pull nomic-embed-text
ollama serve  # Start in separate terminal
```

**Option B: OpenAI**

```bash
# Add to .env
USE_OLLAMA=false
OPENAI_API_KEY=sk-your-key-here
```

### 4. Start Development Servers

```bash
# Terminal 1: Backend
python manage.py runserver

# Terminal 2: Frontend (optional - there's also a vanilla JS frontend)
cd frontend-next
npm install
npm run dev

# Terminal 3: Ollama (if using)
ollama serve
```

**Access the app:**

- Backend API: http://localhost:8000/api/
- Next.js Frontend: http://localhost:3000
- Vanilla JS Frontend: Open `frontend/index.html` or run `cd frontend && python serve.py`

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND LAYER                              │
│                                                                     │
│   Next.js 15 (TypeScript)          Vanilla JS (Single Page)        │
│   ├── App Router                    ├── index.html                  │
│   ├── React Query                   └── app.js                      │
│   └── Tailwind CSS                                                  │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ REST API
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      DJANGO REST FRAMEWORK                          │
│                                                                     │
│   /api/cases/     /api/documents/     /api/chat/     /api/hearings/ │
│   /api/conversations/     /api/gmail/     /api/dashboard/           │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      BUSINESS LOGIC LAYER                           │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  LangGraph AI Pipeline                                        │   │
│  │  route_query → analyze → vector_search → rank → generate →   │   │
│  │  extract_citations → format_response                          │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────┐  ┌─────────────────────┐                  │
│  │  Document Processor │  │  Vector Search      │                  │
│  │  Extract → Chunk →  │  │  Embed query →      │                  │
│  │  Embed → Store      │  │  pgvector search    │                  │
│  └─────────────────────┘  └─────────────────────┘                  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  AI Service Factory → Routes to Ollama OR OpenAI            │   │
│  └─────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      DATA LAYER                                     │
│                                                                     │
│  PostgreSQL + pgvector                                              │
│  ├── cases, hearings, tasks                                         │
│  ├── documents, document_chunks (768-dim vectors)                   │
│  ├── conversations, messages, citations                             │
│  └── emails, gmail_credentials                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Project Structure

```
case-intel/
├── case_intel_project/          # Django settings
├── core/
│   ├── models/                  # 17 Django models
│   ├── views/                   # REST API views
│   ├── serializers/             # DRF serializers
│   ├── services/                # Business logic
│   │   ├── ai_service_factory.py
│   │   ├── ollama_llm_client.py
│   │   ├── document_processor.py
│   │   ├── vector_search_service.py
│   │   └── graph/               # LangGraph pipeline
│   └── admin.py
├── frontend/                    # Vanilla JS SPA
├── frontend-next/               # Next.js 15 app
├── documentations/              # Project docs
├── scripts/                     # Utility scripts
├── requirements.txt
└── manage.py
```

---

## API Reference

### Cases

| Method   | Endpoint           | Description      |
| -------- | ------------------ | ---------------- |
| `GET`    | `/api/cases/`      | List all cases   |
| `POST`   | `/api/cases/`      | Create a case    |
| `GET`    | `/api/cases/{id}/` | Get case details |
| `PATCH`  | `/api/cases/{id}/` | Update a case    |
| `DELETE` | `/api/cases/{id}/` | Delete a case    |

### Documents

| Method   | Endpoint                       | Description     |
| -------- | ------------------------------ | --------------- |
| `GET`    | `/api/documents/`              | List documents  |
| `POST`   | `/api/documents/upload/`       | Upload document |
| `POST`   | `/api/documents/{id}/process/` | Process & embed |
| `DELETE` | `/api/documents/{id}/`         | Delete document |

### AI Chat

| Method | Endpoint     | Description    |
| ------ | ------------ | -------------- |
| `POST` | `/api/chat/` | Ask a question |

**Request:**

```json
{
  "user_query": "What were the key arguments in the motion?",
  "case_id": 1,
  "conversation_id": null
}
```

**Response:**

```json
{
  "answer": "The motion argued that...",
  "confidence": 0.87,
  "query_type": "analysis",
  "citations": [
    {
      "document_id": 5,
      "chunk_id": 12,
      "citation_text": "The court must dismiss..."
    }
  ],
  "conversation_id": 3
}
```

### Hearings

| Method   | Endpoint                       | Description       |
| -------- | ------------------------------ | ----------------- |
| `GET`    | `/api/hearings/`               | List hearings     |
| `GET`    | `/api/hearings/?upcoming=true` | Upcoming hearings |
| `POST`   | `/api/hearings/`               | Create hearing    |
| `PATCH`  | `/api/hearings/{id}/`          | Update hearing    |
| `DELETE` | `/api/hearings/{id}/`          | Delete hearing    |

> **Full API docs:** See [documentations/API_CONTRACTS.md](documentations/API_CONTRACTS.md)

---

## Tech Stack

| Layer                | Technology                                | Purpose                        |
| -------------------- | ----------------------------------------- | ------------------------------ |
| **Frontend**         | Next.js 15, TypeScript, Tailwind CSS      | Modern React framework         |
| **Backend**          | Django 6.0.3, Django REST Framework       | Python web framework           |
| **Database**         | PostgreSQL 15+, pgvector                  | Vector similarity search       |
| **AI Orchestration** | LangGraph                                 | State machine for AI pipelines |
| **LLM (Local)**      | Ollama, llama3.1:8b                       | Local inference                |
| **LLM (Cloud)**      | OpenAI, GPT-4o                            | Cloud inference                |
| **Embeddings**       | nomic-embed-text / text-embedding-3-small | Vector generation              |
| **Document Parsing** | PyPDF2, python-docx                       | Extract text from files        |

---

## Contributing

We welcome contributions! Here's how to get started:

### Development Setup

```bash
# Fork and clone the repo
git clone https://github.com/Bugs0007/CASE_INTEL.git
cd CASE_INTEL

# Create a feature branch
git checkout -b feature/amazing-feature

# Install dev dependencies
pip install -r requirements.txt
cd frontend-next && npm install
```

### Areas to Contribute

| Area                 | Difficulty   | Description                                       |
| -------------------- | ------------ | ------------------------------------------------- |
| **UI Improvements**  | Beginner     | Enhance frontend components, add dark mode        |
| **Document Types**   | Beginner     | Add support for more file formats (Excel, images) |
| **API Tests**        | Intermediate | Expand test coverage for REST endpoints           |
| **Search Filters**   | Intermediate | Add date range, document type filters             |
| **Authentication**   | Intermediate | Implement user auth & multi-tenancy               |
| **Streaming**        | Advanced     | Stream LLM responses in real-time                 |
| **RAG Improvements** | Advanced     | Hybrid search, re-ranking algorithms              |
| **Mobile App**       | Advanced     | React Native or Flutter client                    |

### Contribution Guidelines

1. **Fork** the repository
2. Create a **feature branch** (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. Open a **Pull Request**

### Code Style

- **Python:** Follow PEP 8, use type hints
- **TypeScript:** ESLint + Prettier configuration included
- **Commits:** Use conventional commits (`feat:`, `fix:`, `docs:`)

---

## Configuration

### Environment Variables

```bash
# Database
DB_NAME=case_intel
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# AI Provider (switch with one variable)
USE_OLLAMA=true

# Ollama (if USE_OLLAMA=true)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text

# OpenAI (if USE_OLLAMA=false)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# Gmail Integration (optional)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

---

## Testing

```bash
# Backend tests
python manage.py test core

# Test Ollama integration
python test_ollama_integration.py

# Frontend tests (coming soon)
cd frontend-next && npm test
```

---

## Roadmap

- [x] Core case & document management
- [x] LangGraph AI pipeline
- [x] Ollama local LLM support
- [x] Gmail integration
- [x] Next.js frontend
- [ ] User authentication & multi-tenancy
- [ ] Real-time streaming responses
- [ ] OCR for scanned documents
- [ ] Mobile application
- [ ] Advanced analytics dashboard

---

## Documentation

| Document                                                  | Description                |
| --------------------------------------------------------- | -------------------------- |
| [QUICKSTART.md](documentations/QUICKSTART.md)             | 3-minute setup guide       |
| [ARCHITECTURE.md](documentations/ARCHITECTURE.md)         | System design & data flows |
| [API_CONTRACTS.md](documentations/API_CONTRACTS.md)       | Complete API reference     |
| [DB_SCHEMA.md](documentations/DB_SCHEMA.md)               | Database schema            |
| [OLLAMA_SETUP.md](documentations/OLLAMA_SETUP.md)         | Local AI configuration     |
| [PROJECT_OVERVIEW.md](documentations/PROJECT_OVERVIEW.md) | Tabular project summary    |

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Support

- **Repository:** [github.com/Bugs0007/CASE_INTEL](https://github.com/Bugs0007/CASE_INTEL)
- **Questions?** Open an issue or reach out to the maintainers

---

<p align="center">
  <strong>Built with Django, Next.js, and LangGraph</strong><br>
  <em>Star this repo if you find it useful!</em>
</p>

<p align="center">
  <a href="https://github.com/Bugs0007/CASE_INTEL">
    <img src="https://img.shields.io/github/stars/Bugs0007/CASE_INTEL?style=for-the-badge&color=yellow" alt="Star on GitHub"/>
  </a>
</p>
