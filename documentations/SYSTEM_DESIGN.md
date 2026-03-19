# Case Intel System Design

## 1. DATABASE ARCHITECTURE

### Core Models & Relationships

```
Case (Parent)
├── Documents (1:N) → File storage, chunking, embeddings
├── Conversations (1:N) → Chat sessions
└── Tasks, ActivityLogs, etc.

Document (Parent)
├── DocumentChunk (1:N) → Vector embeddings (768-dim for Ollama, 1536 for OpenAI)
├── Folder (1:1) → Hierarchical folder structure
└── Versions, Tags, Attachments

Conversation (Parent)
└── Messages (1:N) → User/Assistant exchanges
    └── Citations (1:N) → References to source documents

Folder
├── Documents (1:N)
└── Subfolders (Self-referencing 1:N) → Recursive hierarchy
```

### Tables & Columns

| Model | Key Columns | Purpose |
|-------|-----------|---------|
| **Case** | case_number, title, client_name, status, priority, case_type, filing_date | Legal case metadata |
| **Document** | filename, file_path, file_type, processing_status, chunk_count, extracted_text | Document storage & tracking |
| **DocumentChunk** | document_id, text, embedding (pgvector 768d), chunk_index | Vector search index |
| **Conversation** | case_id, title, started_at, last_message_at | Chat sessions |
| **Message** | conversation_id, role (user/assistant), content, created_at | Chat history |
| **Citation** | message_id, document_id, chunk_id, citation_text, source_type | Source attribution |
| **Folder** | name, parent_folder_id | Hierarchical folders |

### Key Constraints
- Document.case_id is optional → documents can exist without a case
- Document.folder_id is optional → documents can exist without a folder
- Conversation requires a case_id
- DocumentChunk embeddings are dynamic: 768-dim (Ollama) or 1536-dim (OpenAI)

---

## 2. API CONTRACTS

### Base URL
```
http://localhost:8000/api/
```

### A. CASE MANAGEMENT

#### Create Case
```
POST /api/cases/
Content-Type: application/json

{
  "case_number": "2024-001",
  "title": "Smith v. Jones",
  "client_name": "Sarah Smith",
  "opposing_party": "John Jones",
  "case_type": "civil",
  "status": "open",
  "priority": "high",
  "filing_date": "2024-01-15",
  "notes": "Commercial dispute over contract"
}

Response: 201 Created
{
  "id": 1,
  "case_number": "2024-001",
  "title": "Smith v. Jones",
  "client_name": "Sarah Smith",
  "case_type": "civil",
  "status": "open",
  "priority": "high",
  "document_count": 0,
  "created_at": "2024-01-15T10:00:00Z"
}
```

#### List Cases
```
GET /api/cases/

Response: 200 OK
[
  {
    "id": 1,
    "case_number": "2024-001",
    "title": "Smith v. Jones",
    "status": "open",
    "document_count": 5,
    ...
  }
]
```

#### Get Case Details
```
GET /api/cases/{id}/
Response: 200 OK { ...case... }
```

#### Update Case
```
PATCH /api/cases/{id}/
Content-Type: application/json
{ "status": "closed", "notes": "Updated notes" }
Response: 200 OK { ...updated case... }
```

#### Delete Case
```
DELETE /api/cases/{id}/
Response: 204 No Content
```

---

### B. DOCUMENT MANAGEMENT

#### Upload Document
```
POST /api/documents/upload/
Content-Type: multipart/form-data

Form Fields:
  - file: <binary file> (required)
  - case_id: integer (optional)
  - document_type: string (optional)
    Choices: contract|pleading|evidence|correspondence|brief|motion|order|other

Response: 201 Created
{
  "id": 5,
  "case_id": 1,
  "filename": "motion.pdf",
  "file_type": "pdf",
  "file_size": 102400,
  "document_type": "motion",
  "processing_status": "pending",
  "chunk_count": null,
  "created_at": "2024-01-20T14:30:00Z"
}
```

#### List Documents
```
GET /api/documents/
GET /api/documents/?case_id=1  # Filter by case

Response: 200 OK
[
  {
    "id": 5,
    "case_id": 1,
    "filename": "motion.pdf",
    "processing_status": "pending",
    "chunk_count": null,
    ...
  }
]
```

#### Get Document Details
```
GET /api/documents/{id}/
Response: 200 OK { ...document... }
```

#### Delete Document
```
DELETE /api/documents/{id}/
Response: 204 No Content
```

#### Process Document (Extract & Embed)
```
POST /api/documents/{id}/process/

Response: 200 OK
{
  "id": 5,
  "filename": "motion.pdf",
  "processing_status": "completed",
  "chunk_count": 12,
  "extracted_text": "Motion to Dismiss...",
  ...
}
```

---

### C. CONVERSATIONAL AI

#### Query LLM with Vector Search
```
POST /api/chat/
Content-Type: application/json

{
  "query": "What were the key arguments in the motion?",
  "case_id": 1,           # optional - scopes search to this case
  "conversation_id": 5    # optional - continues existing conversation
}

Response: 200 OK
{
  "answer": "The motion argued that... [comprehensive AI response]",
  "confidence": 0.87,
  "query_type": "analysis",
  "requires_clarification": false,
  "clarification_question": null,
  "message_id": 42,
  "conversation_id": 5,
  "citations": [
    {
      "id": 101,
      "source_type": "document_chunk",
      "document_id": 5,
      "chunk_id": 3,
      "citation_text": "The court must dismiss...",
      "created_at": "2024-01-20T14:35:00Z"
    }
  ]
}
```

#### List Conversations
```
GET /api/conversations/

Response: 200 OK
[
  {
    "id": 5,
    "case_id": 1,
    "title": "Motion Analysis",
    "started_at": "2024-01-20T14:30:00Z",
    "last_message_at": "2024-01-20T14:35:00Z"
  }
]
```

#### Get Conversation Details
```
GET /api/conversations/{id}/

Response: 200 OK
{
  "id": 5,
  "case_id": 1,
  "title": "Motion Analysis",
  "messages": [
    {
      "id": 40,
      "role": "user",
      "content": "What were the key arguments?",
      "created_at": "2024-01-20T14:30:00Z"
    },
    {
      "id": 41,
      "role": "assistant",
      "content": "The motion argued that...",
      "created_at": "2024-01-20T14:32:00Z",
      "citations": [...]
    }
  ]
}
```

#### Delete Conversation
```
DELETE /api/conversations/{id}/
Response: 204 No Content
```

---

## 3. WORKFLOW

### Document Upload & Processing Flow
```
1. User uploads file → POST /documents/upload/
   ✓ File validated (extension, size)
   ✓ File saved to disk
   ✓ Document record created (status: "pending")

2. User triggers processing → POST /documents/{id}/process/
   ✓ Document status → "processing"
   ✓ Extract text from PDF/DOCX
   ✓ Split into semantic chunks
   ✓ Generate embeddings (768d or 1536d)
   ✓ Save DocumentChunk records
   ✓ Document status → "completed"
```

### AI Query Flow
```
1. User submits query → POST /api/chat/
   {query, case_id?, conversation_id?}

2. Backend processes:
   ✓ Route query → analyze type (search/analysis/clarification)
   ✓ Vector search → find similar chunks
   ✓ Rank chunks → by relevance score
   ✓ Generate answer → LLM (Ollama or OpenAI)
   ✓ Extract citations → link to sources
   ✓ Save Message → conversation history

3. Return response with citations
```

---

## 4. MINIMAL FRONTEND DESIGN

### Tech Stack (KISS Principle)
- **HTML5 + CSS3 + Vanilla JS** → No frameworks
- **Fetch API** → No jQuery/Axios
- **LocalStorage** → Simple session management
- **Single index.html** → One file to deploy

### Page Routes
```
/                     → Dashboard (list cases)
/?case={id}           → Case details + documents
/?chat={conversation} → Chat view
```

### Components

#### A. CASE SIDEBAR (Left Panel)
```
┌─────────────────────────────────┐
│ 📁 CASE INTEL                   │
├─────────────────────────────────┤
│ [New Case] [Settings]           │
├─────────────────────────────────┤
│ Active Cases                     │
│ ──────────────────────────────   │
│ ☐ Case 2024-001                │
│   Smith v. Jones                │
│   5 Documents                   │
│─────────────────────────────────│
│ ☐ Case 2024-002                │
│   Brown v. Smith                │
│   3 Documents                   │
└─────────────────────────────────┘
```

#### B. CASE DETAILS PANEL (Center)
```
┌──────────────────────────────────────┐
│ Case 2024-001: Smith v. Jones        │
├──────────────────────────────────────┤
│ Status: [Open ▼]  Priority: [High ▼] │
│ Client: Sarah Smith                  │
│ Opposing: John Jones                 │
│ Filed: 2024-01-15                    │
├──────────────────────────────────────┤
│ 📄 DOCUMENTS                         │
│ ──────────────────────────────────   │
│ ☐ motion.pdf          [Process] [🗑] │
│   Status: Pending                    │
│ ✓ brief.pdf           [Delete]       │
│   Status: Completed • 12 chunks      │
│ ☐ evidence.docx       [Process]      │
│   Status: Pending                    │
├──────────────────────────────────────┤
│ [Upload Document] [Chat with AI]     │
└──────────────────────────────────────┘
```

#### C. DOCUMENT UPLOAD MODAL
```
┌────────────────────────────────────┐
│ ✕ Upload Document                  │
├────────────────────────────────────┤
│ Document Type:                     │
│ [Contract ▼]                       │
│                                    │
│ Drop files here or:                │
│ [Browse Files]                     │
│ (Allowed: PDF, DOCX, DOC, TXT)     │
│ (Max: 50 MB)                       │
│                                    │
│        [Cancel] [Upload]           │
└────────────────────────────────────┘
```

#### D. CHAT PANEL (Right)
```
┌─────────────────────────────────────┐
│ 💬 Chat: Smith v. Jones (Case ID:1) │
├─────────────────────────────────────┤
│                                     │
│ You: What were the key arguments?  │
│ 12:34 PM                           │
│                                     │
│ Assistant:                          │
│ The motion argued that the court..  │
│ [📎 Citation 1] [📎 Citation 2]    │
│ 12:36 PM                           │
│                                     │
│ Confidence: ████████░░ 87%         │
│ Query Type: Analysis                │
│                                     │
├─────────────────────────────────────┤
│ [Type your question...]             │
│ [Send ➤]                            │
│                                     │
│ Views:                              │
│ [Conversation History] [New Chat]   │
└─────────────────────────────────────┘
```

---

## 5. FRONTEND HTML STRUCTURE

### Single-Page App Layout
```html
<!DOCTYPE html>
<html>
<head>
  <title>Case Intel</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto;
      display: grid;
      grid-template-columns: 250px 1fr 350px;
      gap: 0;
      min-height: 100vh;
      background: #f5f5f5;
    }

    .sidebar { background: #2c3e50; color: white; padding: 20px; overflow-y: auto; }
    .main { background: white; padding: 20px; overflow-y: auto; }
    .chat { background: #ecf0f1; padding: 20px; display: flex; flex-direction: column; }

    .case-item {
      padding: 10px;
      margin: 5px 0;
      background: #34495e;
      border-radius: 4px;
      cursor: pointer;
    }

    .case-item:hover { background: #3d5a7f; }
    .case-item.active { background: #e74c3c; }

    .document {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px;
      background: #ecf0f1;
      margin: 5px 0;
      border-radius: 4px;
    }

    .message {
      margin: 10px 0;
      padding: 10px;
      border-radius: 4px;
      background: white;
    }

    .message.user { background: #3498db; color: white; margin-left: auto; }
    .message.assistant { background: white; }

    input, textarea, select {
      width: 100%;
      padding: 8px;
      margin: 5px 0;
      border: 1px solid #bdc3c7;
      border-radius: 4px;
      font-family: inherit;
    }

    button {
      padding: 8px 15px;
      background: #3498db;
      color: white;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      margin: 5px;
    }

    button:hover { background: #2980b9; }
  </style>
</head>
<body>

<div class="sidebar">
  <h2>📁 Case Intel</h2>
  <button onclick="showNewCaseModal()">+ New Case</button>
  <div id="cases-list"></div>
</div>

<div class="main">
  <div id="case-details"></div>
</div>

<div class="chat">
  <h3 id="chat-title">Chat</h3>
  <div id="messages" style="flex: 1; overflow-y: auto; margin: 10px 0;"></div>
  <div>
    <textarea id="query" placeholder="Ask a question..." rows="3"></textarea>
    <button onclick="sendChat()">Send ➤</button>
  </div>
</div>

<!-- Modals -->
<div id="upload-modal" style="display: none; position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background: white; padding: 20px; border-radius: 8px; z-index: 1000; width: 400px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
  <h3>Upload Document</h3>
  <select id="doc-type">
    <option value="contract">Contract</option>
    <option value="pleading">Pleading</option>
    <option value="evidence">Evidence</option>
    <option value="motion">Motion</option>
    <option value="other">Other</option>
  </select>
  <input type="file" id="doc-file" accept=".pdf,.docx,.doc,.txt">
  <button onclick="uploadDocument()">Upload</button>
  <button onclick="closeModal('upload-modal')">Cancel</button>
</div>

<script src="app.js"></script>

</body>
</html>
```

### app.js - Core Logic
```javascript
const API_BASE = 'http://localhost:8000/api';
let currentCaseId = null;
let currentConversationId = null;

// === CASE MANAGEMENT ===

async function loadCases() {
  const res = await fetch(`${API_BASE}/cases/`);
  const cases = await res.json();
  const list = document.getElementById('cases-list');
  list.innerHTML = cases.map(c => `
    <div class="case-item" onclick="selectCase(${c.id})">
      <strong>${c.case_number}</strong><br>
      ${c.title}<br>
      <small>${c.document_count} docs</small>
    </div>
  `).join('');
}

async function selectCase(caseId) {
  currentCaseId = caseId;
  const res = await fetch(`${API_BASE}/cases/${caseId}/`);
  const caseData = await res.json();

  // Display case details
  let html = `
    <h2>${caseData.case_number}: ${caseData.title}</h2>
    <p><strong>Client:</strong> ${caseData.client_name}</p>
    <p><strong>Status:</strong> ${caseData.status}</p>
    <h3>Documents</h3>
  `;

  // Load documents for this case
  const docRes = await fetch(`${API_BASE}/documents/?case_id=${caseId}`);
  const docs = await docRes.json();

  html += docs.map(d => `
    <div class="document">
      <div>
        ${d.filename} (${d.processing_status})
        ${d.chunk_count ? `• ${d.chunk_count} chunks` : ''}
      </div>
      <div>
        ${d.processing_status === 'pending' ? `<button onclick="processDoc(${d.id})">Process</button>` : ''}
        <button onclick="deleteDoc(${d.id})">Delete</button>
      </div>
    </div>
  `).join('');

  html += '<button onclick="showUploadModal()">+ Upload Document</button>';
  html += '<button onclick="newChat()">💬 Chat with AI</button>';

  document.getElementById('case-details').innerHTML = html;
}

// === DOCUMENT UPLOAD ===

async function uploadDocument() {
  const file = document.getElementById('doc-file').files[0];
  const docType = document.getElementById('doc-type').value;

  const formData = new FormData();
  formData.append('file', file);
  formData.append('case_id', currentCaseId);
  formData.append('document_type', docType);

  const res = await fetch(`${API_BASE}/documents/upload/`, {
    method: 'POST',
    body: formData
  });

  if (res.ok) {
    alert('Document uploaded!');
    closeModal('upload-modal');
    selectCase(currentCaseId); // Refresh
  } else {
    const err = await res.json();
    alert(`Error: ${err.detail}`);
  }
}

async function processDoc(docId) {
  const res = await fetch(`${API_BASE}/documents/${docId}/process/`, {
    method: 'POST'
  });

  if (res.ok) {
    alert('Processing started!');
    selectCase(currentCaseId); // Refresh
  }
}

// === CHAT ===

async function newChat() {
  currentConversationId = null;
  document.getElementById('messages').innerHTML = '';
  document.getElementById('chat-title').textContent = `Chat with Case ${currentCaseId}`;
}

async function sendChat() {
  const query = document.getElementById('query').value.trim();
  if (!query) return;

  // Display user message
  addMessage('user', query);
  document.getElementById('query').value = '';

  // Call AI endpoint
  const res = await fetch(`${API_BASE}/chat/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      case_id: currentCaseId,
      conversation_id: currentConversationId
    })
  });

  const data = await res.json();

  currentConversationId = data.conversation_id;

  // Display AI response
  let answerHtml = data.answer;
  if (data.citations && data.citations.length > 0) {
    answerHtml += '<div style="margin-top: 10px; font-size: 0.9em; color: #666;">';
    answerHtml += '<strong>Sources:</strong><br>';
    data.citations.forEach((c, i) => {
      answerHtml += `📎 Citation ${i + 1}: ${c.citation_text.substring(0, 100)}...<br>`;
    });
    answerHtml += '</div>';
  }

  addMessage('assistant', answerHtml);
  addMessage('info', `Confidence: ${(data.confidence * 100).toFixed(0)}%`);
}

function addMessage(role, content) {
  const msg = document.createElement('div');
  msg.className = `message ${role}`;
  msg.innerHTML = content;
  document.getElementById('messages').appendChild(msg);
  document.getElementById('messages').scrollTop = document.getElementById('messages').scrollHeight;
}

// === UI HELPERS ===

function showUploadModal() {
  document.getElementById('upload-modal').style.display = 'block';
}

function closeModal(modalId) {
  document.getElementById(modalId).style.display = 'none';
}

function showNewCaseModal() {
  const caseNumber = prompt('Case Number:');
  const title = prompt('Case Title:');
  const client = prompt('Client Name:');

  if (caseNumber && title && client) {
    fetch(`${API_BASE}/cases/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        case_number: caseNumber,
        title,
        client_name: client,
        status: 'open',
        priority: 'medium'
      })
    }).then(() => loadCases());
  }
}

async function deleteDoc(docId) {
  if (confirm('Delete this document?')) {
    await fetch(`${API_BASE}/documents/${docId}/`, { method: 'DELETE' });
    selectCase(currentCaseId);
  }
}

// === INIT ===
loadCases();
```

---

## 6. FILES STRUCTURE

```
CASE_INTEL/
├── frontend/
│   ├── index.html          ← Main HTML (this file)
│   ├── app.js              ← JavaScript logic
│   ├── styles.css          ← CSS (can be moved to <style> tag)
│   └── serve.py            ← Simple Python server (python serve.py)
├── case_intel_project/
│   ├── settings.py
│   ├── wsgi.py
│   └── urls.py
├── core/
│   ├── models/
│   ├── views/
│   ├── serializers/
│   ├── services/
│   └── urls.py
└── manage.py
```

---

## 7. QUICK START

### Backend
```bash
# Terminal 1: Start Django & Ollama
python manage.py runserver 8000

# Terminal 2: Start Ollama (if not running)
ollama serve

# Terminal 3: Process documents (if needed)
python manage.py shell
>>> from core.models import Document
>>> from core.services.document_processor import DocumentProcessor
>>> proc = DocumentProcessor()
>>> proc.process_document(1)
```

### Frontend
```bash
# Terminal: Serve frontend
cd frontend
python -m http.server 8080
# Visit http://localhost:8080
```

---

## 8. USAGE FLOW

```
1. User opens http://localhost:8080
   ↓
2. Sidebar loads list of cases
   ↓
3. User clicks case → Shows case details & documents
   ↓
4. User uploads documents → POST /documents/upload/
   ↓
5. User clicks "Process" → Extracts text & creates embeddings
   ↓
6. User clicks "Chat" → Opens chat panel
   ↓
7. User types query → POST /chat/ with vector search & LLM
   ↓
8. Response shows answer + citations + confidence score
   ↓
9. Conversation saved to database for history
```

---

## KEY FEATURES

✅ **Simple**: Single HTML file + vanilla JS
✅ **No Dependencies**: Works with pure fetch API
✅ **Real-time Processing**: Document embedding & AI responses
✅ **Citation Tracking**: See which documents AI used
✅ **Multi-case Support**: Organize by legal cases
✅ **Conversation History**: Saved in database
✅ **Ollama or OpenAI**: Backend configurable, frontend agnostic

---

## ERROR HANDLING

| Scenario | Response |
|----------|----------|
| File too large | 400 Bad Request: "File size exceeds X MB" |
| Invalid file type | 400 Bad Request: "Unsupported file type" |
| Case not found | 404 Not Found |
| Document processing failed | 500 Server Error + logs |
| Network error | JS fetch error → user alert |

---

## DEPLOYMENT

### Local Development
- Backend: http://localhost:8000
- Frontend: http://localhost:8080 (or serve from Django static files)

### Production
- Disable CORS restrictions (or use Django CORS headers)
- Frontend can be served from Django `static/` directory
- Use gunicorn + nginx for backend
- Enable SSL/TLS

