# ⚡ Quick Start Guide - Case Intel

## 3-Minute Setup

### Prerequisites
- Python 3.10+
- PostgreSQL running
- Ollama or OpenAI API key

### Step 1: Start Django Backend (Terminal 1)

```bash
cd /path/to/CASE_INTEL

# Run migrations if needed
python manage.py migrate

# Start server
python manage.py runserver 8000
```

✅ You should see: `Starting development server at http://127.0.0.1:8000/`

### Step 2: Start Ollama (Terminal 2, if using local LLM)

```bash
ollama serve
```

✅ You should see: `listening on 127.0.0.1:11434`

### Step 3: Start Frontend (Terminal 3)

```bash
cd frontend
python serve.py
```

✅ You should see: `Server running at: http://localhost:8080`

### Step 4: Open Browser

Navigate to: **http://localhost:8080** ← Click here

---

## First Time Using the App?

### 👉 Do This:

1. **Create a Case**
   - Click **+ New Case** (red button, top left)
   - Fill in: Case Number, Title, Client Name
   - Click **Create Case**

2. **Upload Documents**
   - Select your case from sidebar
   - Click **📤 Upload Document**
   - Drag & drop or click to browse
   - Choose document type (Motion, Contract, Evidence, etc.)
   - Click **Upload Document**

3. **Process Documents**
   - Find the document in the Documents list
   - Click **Process** button
   - Wait a few seconds for embedding (backend will extract text & create vectors)
   - Status changes from "Pending" → "Completed"

4. **Chat with AI**
   - Click **💬 Chat with AI** button
   - Type a question: "What were the key arguments?"
   - AI analyzes documents and responds
   - 📎 Sources show which documents were used

---

## API Health Check

Test if backend is working:

```bash
# Get all cases
curl http://localhost:8000/api/cases/

# Should return: []  (empty list) or list of cases
```

If you get "Connection refused", backend isn't running on port 8000.

---

## Common Issues & Fixes

### ❌ "Failed to load cases"
**Fix:** Start Django backend first (Step 1)

### ❌ "Document upload fails"
**Fix:** Check file type is PDF/DOCX/DOC/TXT and size < 50 MB

### ❌ "Chat returns empty answer"
**Fix:** Make sure documents are processed (status = "Completed")

### ❌ "Ollama connection error"
**Fix:**
```bash
# Start Ollama first
ollama serve

# Pull models if needed
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

### ❌ "Port 8000 already in use"
**Fix:** Change Django port
```bash
python manage.py runserver 8001  # Use 8001 instead
# Then edit frontend/app.js: API_BASE = 'http://localhost:8001/api'
```

---

## What's Happening Behind the Scenes?

### When You Upload a Document:
```
1. File → validated (type, size)
2. File → saved to disk
3. Document record → created in DB
```

### When You Click Process:
```
1. Extract text from PDF/DOCX
2. Split into chunks (semantic paragraphs)
3. Generate embeddings (768-dim for Ollama, 1536-dim for OpenAI)
4. Save embeddings to PostgreSQL (pgvector extension)
```

### When You Ask a Question:
```
1. Your question → vector embedding
2. Vector search → find similar chunks (top 5-10)
3. LLM generates answer based on chunks
4. Citations linked → show which documents were used
5. Conversation saved → database
```

---

## Files Overview

```
frontend/
├── index.html       ← Main UI (single page)
├── app.js           ← All JavaScript logic
├── serve.py         ← Simple server
└── README.md        ← Full documentation

CASE_INTEL/
├── manage.py        ← Django commands
├── core/
│   ├── models/      ← Database models (Case, Document, etc.)
│   ├── views/       ← REST API endpoints
│   ├── services/    ← AI logic (embeddings, LLM, vector search)
│   └── serializers/ ← JSON validators
└── case_intel_project/
    └── settings.py  ← Configuration
```

---

## Environment Variables

Create `.env` in project root:

```bash
# Database
DB_NAME=case_intel
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# AI Provider (choose one)
USE_OLLAMA=true                    # Local LLM (free)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text

# OR for OpenAI:
USE_OLLAMA=false
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

---

## Next Steps

1. **Read SYSTEM_DESIGN.md** - Complete architecture & API docs
2. **Read frontend/README.md** - Frontend features & troubleshooting
3. **Check core/models/** - Understand the database schema
4. **Explore core/views/** - See API endpoint implementations
5. **Try the UI** - Create cases, upload docs, chat with AI!

---

## Tips for Best Results

✅ **Process documents after uploading** - Necessary for AI to search/analyze
✅ **Use clear question phrasing** - "What were the arguments?" not "args?"
✅ **Upload case-relevant documents** - AI searches within case documents
✅ **Check citation sources** - Verify AI used correct documents
✅ **View conversation history** - Revisit past analysis

---

## Need Help?

- **Frontend issues?** → See `frontend/README.md`
- **API contracts?** → See `SYSTEM_DESIGN.md`
- **Database schema?** → See `core/models/`
- **Backend services?** → See `core/services/`

Happy analyzing! 🚀

