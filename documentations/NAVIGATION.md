# 🗺️ Case Intel - Visual Navigation Guide

## Document Reading Order

Start here depending on your interest:

### 👨‍💼 **I just want to use it**
→ Read: `QUICKSTART.md` (5 min)
- 3 terminals, go!
- First time walkthrough
- Troubleshooting

### 🔧 **I want to understand the backend**
→ Read: `SYSTEM_DESIGN.md` (15 min)
- Database schema
- API contracts with examples
- Request/response formats

### 🏗️ **I want to understand the full system**
→ Read: `ARCHITECTURE.md` (20 min)
- System diagrams
- Data flow diagrams
- Service descriptions
- Performance notes

### 💻 **I want to understand the frontend**
→ Read: `frontend/README.md` (10 min)
- Feature list
- Browser compatibility
- Development guide
- Debugging tips

### 🆙 **I want to deploy/extend**
→ Read: `SUMMARY.md` (10 min)
- File structure
- Configuration options
- Common tasks
- Extensibility points

---

## The 5-Second Elevator Pitch

```
Case Intel = Legal Case Management + AI Document Analysis

Frontend:  Single HTML page, vanilla JS, no dependencies
           Upload case documents, ask questions, get AI answers + sources

Backend:   Django REST API + PostgreSQL + pgvector
           Vector search, LLM integration, conversation history

AI:        Configurable: Ollama (local, free) OR OpenAI (cloud, paid)
           7-node LangGraph pipeline for semantic analysis

DB:        14 tables: cases, documents, chunks (with vectors),
           conversations, messages, citations

Result:    Legal brief summarized in seconds, with source citations
```

---

## File Locations at a Glance

```
CASE_INTEL/ (Project Root)
│
├── 📄 QUICKSTART.md              ← START HERE (3-min setup)
├── 📄 SUMMARY.md                 ← This guide
├── 📄 SYSTEM_DESIGN.md           ← DB + API details
├── 📄 ARCHITECTURE.md            ← System design deep-dive
├── 📄 .env.example               ← Configuration template
│
├── 📁 frontend/
│   ├── 📄 index.html             ← Complete UI (single file!)
│   ├── 📄 app.js                 ← Frontend logic
│   ├── 📄 serve.py               ← HTTP server
│   └── 📄 README.md              ← Frontend docs
│
├── 📁 core/
│   ├── 📁 models/
│   │   ├── case.py
│   │   ├── document.py
│   │   ├── conversation.py
│   │   ├── message.py
│   │   └── ... (10 more)
│   │
│   ├── 📁 views/
│   │   ├── case.py               ← /api/cases/
│   │   ├── document.py           ← /api/documents/
│   │   └── chat.py               ← /api/chat/
│   │
│   ├── 📁 serializers/
│   │   ├── case.py
│   │   ├── document.py
│   │   └── chat.py
│   │
│   ├── 📁 services/
│   │   ├── ai_workflow.py        ← LangGraph pipeline
│   │   ├── document_processor.py ← Extract & embed
│   │   ├── vector_search_service.py
│   │   ├── ai_service_factory.py ← Ollama OR OpenAI
│   │   ├── ollama_llm_client.py
│   │   ├── ollama_embedding_service.py
│   │   └── graph/
│   │       ├── state.py          ← LangGraph state
│   │       ├── nodes.py          ← 7 pipeline nodes
│   │       ├── builder.py        ← Build graph
│   │       └── config.py
│   │
│   ├── 📄 urls.py                ← Route to views
│   ├── 📄 admin.py               ← Django admin setup
│   └── 📄 migrations/
│       └── 0002_alter_documentchunk_embedding.py
│
├── 📁 case_intel_project/
│   ├── 📄 settings.py            ← Django config
│   ├── 📄 wsgi.py
│   └── 📄 urls.py
│
├── 📄 manage.py                  ← Django CLI
├── 📄 requirements.txt
└── 📄 db.sqlite3 (or PostgreSQL)
```

---

## Quick Reference: API Endpoints

```bash
# CASES
GET /api/cases/                 # List all
POST /api/cases/                # Create
GET /api/cases/1/               # Get one
PATCH /api/cases/1/             # Update
DELETE /api/cases/1/            # Delete

# DOCUMENTS
POST /api/documents/upload/     # Upload file
GET /api/documents/?case_id=1   # List for case
POST /api/documents/1/process/  # Extract & embed
DELETE /api/documents/1/        # Delete

# AI CHAT
POST /api/chat/                 # Query with search + LLM
{
  "query": "What were the arguments?",
  "case_id": 1,
  "conversation_id": null
}
→ Returns: answer + citations + confidence

# CONVERSATIONS
GET /api/conversations/         # List all
GET /api/conversations/1/       # Get with messages
```

---

## Technology Stack at a Glance

```
Frontend:
├── HTML5          (semantic, accessible)
├── CSS3           (responsive grid)
└── Vanilla JS     (no dependencies!)

Backend:
├── Django 6.0.3   (REST framework)
├── PostgreSQL     (RelDB + pgvector for embeddings)
└── Python 3.10+

AI Providers (Pick One):
├── Ollama         (local: llama3.1:8b, nomic-embed-text)
├── OpenAI         (cloud: gpt-4o, text-embedding-3-small)
└── (Easy to add others!)

Orchestration:
└── LangGraph      (state machine for AI pipeline)
```

---

## Key Concepts

### Vector Search
- Convert text → 768-dimensional vector
- Find similar vectors in database
- Return top-K most similar documents

### Document Chunking
- Split long documents into ~500-token chunks
- Each chunk gets its own embedding
- Enables granular citation tracking

### LangGraph Pipeline
- 7-node state machine
- Route → Analyze → Search → Rank → Generate → Cite → Format
- Handles edge cases (no results, low confidence)

### Citation Tracking
- Every AI answer linked to source documents
- User can verify ("Which document supports claim X?")
- Builds trust in AI responses

### Conversation History
- All queries saved to database
- Context preserved for follow-up questions
- Can revisit and continue conversations

---

## Three-Part System

### Part 1: Upload & Process
```
User uploads PDF
    ↓
Backend extracts text (PDFMiner)
    ↓
Splits into chunks (500 tokens each)
    ↓
Converts to vectors (Ollama or OpenAI)
    ↓
Saves to PostgreSQL with pgvector index
    ↓
Status: "Completed"
```

### Part 2: Vector Search
```
User asks question
    ↓
Convert question to vector
    ↓
Search pgvector index (fast!)
    ↓
Find 10 most similar chunks
    ↓
Return with similarity scores
```

### Part 3: AI Generation
```
Get relevant chunks from search
    ↓
Pass to LLM with instruction
    ↓
LLM generates answer using chunks
    ↓
Extract which chunks were cited
    ↓
Return answer + citations to user
```

---

## Development Workflow

### For Backend Changes
```bash
cd /path/to/CASE_INTEL
python manage.py runserver 8000

# Edit code → Refresh browser
# Django auto-reloads on save
```

### For Frontend Changes
```bash
cd frontend
python serve.py

# Edit index.html or app.js → Refresh browser
# Python server auto-serves changes
```

### For AI Pipeline Changes
```bash
# Edit: core/services/graph/nodes.py
# Changes take effect on next chat query
# Test with: python manage.py shell
```

### For Database Changes
```bash
# Create migration: python manage.py makemigrations
# Apply migration: python manage.py migrate
# Rollback if needed: python manage.py migrate core 0001
```

---

## Quick Commands Reference

```bash
# Start Django
python manage.py runserver 8000

# Start Ollama
ollama serve

# Start Frontend
cd frontend && python serve.py

# Process all pending documents
python manage.py shell
>>> from core.services.document_processor import DocumentProcessor
>>> from core.models import Document
>>> p = DocumentProcessor()
>>> for d in Document.objects.filter(processing_status="pending"):
>>>     p.process_document(d.id)

# View database
python manage.py dbshell

# Test API
curl http://localhost:8000/api/cases/

# Clear all data
python manage.py flush

# Create admin user
python manage.py createsuperuser
# Then visit http://localhost:8000/admin/
```

---

## Testing Checklist

Before claiming "it works", verify:

- [ ] Backend runs on port 8000
- [ ] Ollama or OpenAI configured correctly
- [ ] Frontend loads on port 8080
- [ ] Can create a case
- [ ] Can upload a document
- [ ] Can process a document (status → "Completed")
- [ ] Can ask chat question
- [ ] AI responds with answer + citations
- [ ] Confidence score > 50%
- [ ] Conversation saved to database

---

## Next Actions

1. **Right now**: Open `QUICKSTART.md`
2. **In 5 min**: Have backend running
3. **In 10 min**: Have frontend running
4. **In 15 min**: Create first case
5. **In 20 min**: Upload first document
6. **In 25 min**: Chat with AI about your document

---

## Questions?

| Question | Answer |
|----------|--------|
| "How do I run this?" | → QUICKSTART.md |
| "What database tables exist?" | → SYSTEM_DESIGN.md (schema section) |
| "How does AI answer questions?" | → ARCHITECTURE.md (data flow section) |
| "What are the API endpoints?" | → SYSTEM_DESIGN.md (API contracts) |
| "How do I modify the AI pipeline?" | → core/services/graph/nodes.py |
| "How do I add a new document type?" | → core/models/document.py + migration |
| "Can I use OpenAI instead?" | → Set USE_OLLAMA=false in .env |

---

**Ready?** 🚀

Open **QUICKSTART.md** and follow the 5 steps.

You'll have a working system in **under 10 minutes**.

Then read the docs to understand how it works! 📚
