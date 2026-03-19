# Case Intel Frontend

A minimal, single-page web application for legal case management and AI-powered document analysis.

## Features

✅ **Case Management** - Create and manage legal cases with metadata
✅ **Document Upload** - Upload PDF, DOCX, DOC, or TXT files
✅ **Document Processing** - Extract text and generate embeddings for semantic search
✅ **AI Chat** - Ask questions and get answers powered by LLM with citations
✅ **Citation Tracking** - See which documents the AI used to generate answers
✅ **Conversation History** - Save and view chat conversations
✅ **No Dependencies** - Pure HTML, CSS, and Vanilla JavaScript

## Quick Start

### 1. Start Backend

```bash
# Terminal 1: Django API
cd /path/to/CASE_INTEL
python manage.py runserver 8000

# Terminal 2: Ollama (if using local LLM)
ollama serve
```

### 2. Start Frontend

```bash
# Terminal 3: Frontend server
cd frontend
python serve.py
```

Or use any other HTTP server:

```bash
# Using Python built-in server
python -m http.server 8080

# Using Node http-server
npx http-server -p 8080

# Using VSCode Live Server extension
# Just open index.html and use Live Server
```

### 3. Open in Browser

Navigate to: **http://localhost:8080**

## API Configuration

The frontend is hardcoded to connect to `http://localhost:8000/api`.

If your Django backend runs on a different port or URL, edit `app.js`:

```javascript
const API_BASE = "http://localhost:8000/api"; // Change this line
```

## Usage

### Creating a Case

1. Click **"+ New Case"** in the sidebar
2. Fill in case details (Case Number, Title, Client Name, etc.)
3. Click **"Create Case"**

### Uploading Documents

1. Select a case from the sidebar
2. Click **"📤 Upload Document"**
3. Choose document type (Contract, Motion, Evidence, etc.)
4. Drop files or click to browse (PDF, DOCX, DOC, TXT - Max 50 MB)
5. Click **"Upload Document"**

### Processing Documents

1. In the Documents section, find uploaded document with "Pending" status
2. Click **"Process"** button
3. Backend will:
   - Extract text from the file
   - Split into semantic chunks
   - Generate vector embeddings
   - Status changes to "Completed"

### Chatting with AI

1. Select a case
2. Click **"💬 Chat with AI"**
3. Type questions like:
   - "What were the key arguments in the motion?"
   - "Summarize the evidence section"
   - "Find contradictions in the documents"
4. AI responds with answers and citations
5. Citations show which documents were used

### Viewing Chat History

- Conversations are saved automatically
- Go to **Conversations** tab to see past chats
- Click a conversation to continue it

## Architecture

```
Frontend (Vanilla JS)
    ↓
Fetch API
    ↓
Django REST Backend (http://localhost:8000/api)
    ↓
PostgreSQL + pgvector
    ↓
LLM (Ollama local or OpenAI)
```

## API Endpoints Used

| Method | Endpoint                       | Purpose                  |
| ------ | ------------------------------ | ------------------------ |
| GET    | `/api/cases/`                  | List all cases           |
| POST   | `/api/cases/`                  | Create new case          |
| GET    | `/api/cases/{id}/`             | Get case details         |
| PATCH  | `/api/cases/{id}/`             | Update case              |
| DELETE | `/api/cases/{id}/`             | Delete case              |
| POST   | `/api/documents/upload/`       | Upload document          |
| GET    | `/api/documents/?case_id={id}` | List documents for case  |
| DELETE | `/api/documents/{id}/`         | Delete document          |
| POST   | `/api/documents/{id}/process/` | Process document         |
| POST   | `/api/chat/`                   | Ask AI question          |
| GET    | `/api/conversations/`          | List conversations       |
| GET    | `/api/conversations/{id}/`     | Get conversation details |

## Troubleshooting

### Frontend loads but shows "Failed to load cases"

- Check that Django backend is running on port 8000
- Check browser console (F12) for CORS errors
- Ensure `API_BASE` in `app.js` matches your backend URL

### Document upload fails

- Check file type (only PDF, DOCX, DOC, TXT allowed)
- Check file size (max 50 MB)
- Check Django logs for detailed error

### Chat returns "Case not found"

- Make sure you've selected a case before chatting
- Check that case exists in database

### Chat response is incomplete or generic

- Ensure documents are processed (status = "Completed")
- Check vector search is finding relevant chunks
- If using Ollama, verify it's running and models are loaded

## Development

### Modifying Styles

Edit the `<style>` section in `index.html` or move to external `styles.css`

### Adding Features

Main logic is in `app.js`. Key functions:

- `loadCases()` - Fetch and display cases
- `selectCase(id)` - Load case details
- `sendChat()` - Send query to AI
- `uploadDocument()` - Upload file
- `processDocument(id)` - Trigger processing

### Debugging

Open browser DevTools (F12):

- Network tab: See API requests/responses
- Console tab: JavaScript errors
- Application tab: LocalStorage and state

## Performance Notes

- Frontend is lightweight (~50 KB uncompressed)
- No external dependencies = fast load time
- Vanilla JS = minimal overhead
- Suitable for embedding in Electron/Tauri apps

## Browser Support

- Chrome/Edge: ✅ Full support
- Firefox: ✅ Full support
- Safari: ✅ Full support (11+)
- IE: ❌ Not supported (uses modern ES6 features)

## License

Part of Case Intel project. See main project README for license details.

---

Need help? Check the main CASE_INTEL documentation or see SYSTEM_DESIGN.md for full architecture details.
