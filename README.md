# Case Intel - Legal Case Management AI Platform

A Django REST API for legal case management with AI-powered document search and Q&A using LangGraph workflows.

## Features

- **Document Management**: Upload and organize legal documents (PDF, DOCX, TXT)
- **Semantic Search**: Vector-based search using pgvector and embeddings
- **AI Q&A**: Ask questions about documents using LangGraph AI workflows
- **Conversation History**: Track conversations and citations
- **Flexible AI Backend**: Switch between OpenAI (cloud) and Ollama (local) with one setting

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 15+ with pgvector extension
- Ollama (for local AI) OR OpenAI API key

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Case_INTEL
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

5. **Run migrations**
   ```bash
   python manage.py migrate
   ```

6. **Start server**
   ```bash
   python manage.py runserver
   ```

API will be available at `http://localhost:8000/api/`

## AI Backend Setup

### Option 1: Ollama (Recommended for Privacy)

**100% local, zero API costs, complete privacy**

1. **Install Ollama**: Visit [ollama.ai](https://ollama.ai)

2. **Download models**:
   ```bash
   ollama pull llama3.1:8b
   ollama pull nomic-embed-text
   ```

3. **Update .env**:
   ```bash
   USE_OLLAMA=true
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=llama3.1:8b
   OLLAMA_EMBEDDING_MODEL=nomic-embed-text
   ```

4. **Start Ollama server**:
   ```bash
   ollama serve
   ```

5. **Run database migration** (changes embedding dimensions from 1536 to 768):
   ```bash
   python manage.py migrate
   ```

6. **Test integration**:
   ```bash
   python test_ollama_integration.py
   ```

See [OLLAMA_SETUP.md](OLLAMA_SETUP.md) for detailed setup guide.

### Option 2: OpenAI (Cloud-based)

**GPT-4o for superior quality, requires API key**

1. **Get OpenAI API key**: https://platform.openai.com/api-keys

2. **Update .env**:
   ```bash
   USE_OLLAMA=false
   OPENAI_API_KEY=sk-your-api-key-here
   OPENAI_MODEL=gpt-4o
   OPENAI_EMBEDDING_MODEL=text-embedding-3-small
   ```

3. **Run migrations**:
   ```bash
   python manage.py migrate
   ```

## API Endpoints

### Documents
- `POST /api/documents/upload/` - Upload a document
- `GET /api/documents/` - List documents
- `GET /api/documents/{id}/` - Get document details
- `POST /api/documents/{id}/process/` - Process document (generate embeddings)
- `DELETE /api/documents/{id}/` - Delete document

### Cases
- `GET /api/cases/` - List cases
- `POST /api/cases/` - Create case
- `GET /api/cases/{id}/` - Get case details
- `PATCH /api/cases/{id}/` - Update case
- `DELETE /api/cases/{id}/` - Delete case

### Chat & Q&A
- `POST /api/chat/` - Ask a question about documents
  ```json
  {
    "user_query": "What were the key arguments in the motion?",
    "case_id": 1,
    "conversation_id": 5  // optional
  }
  ```

### Conversations
- `GET /api/conversations/` - List conversations
- `GET /api/conversations/{id}/` - Get conversation details
- `DELETE /api/conversations/{id}/` - Delete conversation

## Architecture

### Models (14 total)
- `Case` - Legal case
- `Document` - Case documents with metadata
- `DocumentChunk` - Text chunks with pgvector embeddings
- `Conversation` - Chat sessions
- `Message` - Chat messages
- `Citation` - References to source documents
- And more for tags, versions, emails, etc.

### Services
- **AIWorkflowService** - Orchestrates LangGraph pipeline
- **LLMClient** / **OllamaLLMClient** - Chat completion interfaces
- **EmbeddingService** / **OllamaEmbeddingService** - Text embedding generators
- **AIServiceFactory** - Routes to correct backend based on `USE_OLLAMA` setting
- **VectorSearchService** - pgvector semantic search
- **DocumentProcessor** - Document ingestion pipeline

### LangGraph Workflow
```
route_query
    ├─ clarify → END
    └─ analyze_query
        └─ vector_search
            ├─ no_results → handle_no_results → END
            ├─ low_confidence → handle_low_confidence → extract_citations → format_response → END
            └─ rank_chunks → generate_answer → extract_citations → format_response → END
```

## Configuration

### Environment Variables

```bash
# Database
DB_NAME=case_intel
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# AI Provider (Use EITHER Ollama OR OpenAI)
USE_OLLAMA=true                          # or false

# OpenAI (if USE_OLLAMA=false)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# Ollama (if USE_OLLAMA=true)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text

# AI Workflow
AI_SEARCH_TOP_K=10
AI_RERANK_TOP_K=5
AI_CONFIDENCE_THRESHOLD=0.5
AI_MAX_CONVERSATION_HISTORY=5
```

## Testing

### Integration Tests

Test Ollama integration:
```bash
python test_ollama_integration.py
```

Tests:
- ✓ Ollama connection
- ✓ Embedding generation
- ✓ LLM text generation
- ✓ JSON mode
- ✓ Factory pattern

### Unit Tests

Run Django tests:
```bash
python manage.py test core
```

## Performance

### Embedding Dimensions
- OpenAI text-embedding-3-small: 1536
- Ollama nomic-embed-text: 768

**Note**: Database schema must match selected embedding model. Migration `0002_alter_documentchunk_embedding` handles the switch.

### Response Times

| Operation | Ollama | OpenAI |
|-----------|--------|--------|
| Embed text | 100ms | 50ms |
| Vector search | <100ms | <100ms |
| LLM response | 50-200ms/token | 30-100ms/token |
| Full Q&A | 1-5s | 1-3s |

## Development

### Project Structure
```
Case_INTEL/
├── case_intel_project/          # Django project settings
├── core/
│   ├── models/                  # ORM models
│   ├── views/                   # REST API views
│   ├── serializers/             # DRF serializers
│   ├── services/                # Business logic
│   │   ├── ai_service_factory.py
│   │   ├── ollama_llm_client.py
│   │   ├── ollama_embedding_service.py
│   │   ├── graph/               # LangGraph workflow
│   │   └── ...
│   ├── migrations/              # Database migrations
│   └── admin.py                 # Django admin config
├── scripts/                     # Utility scripts
│   └── migrate_to_ollama.py    # Re-embed documents
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment template
├── manage.py                    # Django management
├── test_ollama_integration.py   # Integration tests
├── OLLAMA_SETUP.md             # Ollama guide
└── README.md                   # This file
```

### Making Changes

1. **Add a model**: `core/models/new_model.py`
2. **Create serializer**: `core/serializers/new_model.py`
3. **Add view**: `core/views/new_model.py`
4. **Register URL**: `core/urls.py`
5. **Run migrations**: `python manage.py makemigrations && python manage.py migrate`

## Troubleshooting

### Database Connection Error
```
FATAL: password authentication failed for user "postgres"
```
- Check `.env` database credentials
- Ensure PostgreSQL is running
- Verify pgvector extension: `CREATE EXTENSION IF NOT EXISTS vector;`

### Ollama Connection Error
```
Cannot connect to Ollama at http://localhost:11434
```
- Start Ollama: `ollama serve`
- Check `OLLAMA_BASE_URL` in `.env`
- Verify models: `ollama list`

### Embedding Dimension Mismatch
```
Dimension mismatch: expected 768, got 1536
```
- You switched providers but didn't migrate
- Run: `python manage.py migrate`
- Re-process documents: See [OLLAMA_SETUP.md](OLLAMA_SETUP.md)

### Out of Memory
- Reduce model: `ollama pull mistral:7b`
- Check system RAM: `free -h` (Linux) or Task Manager (Windows)
- Close other applications

See [OLLAMA_SETUP.md](OLLAMA_SETUP.md) for more troubleshooting.

## Integration with External Tools

### Postman Collection
Import the provided Postman collection to test all API endpoints directly.

### Python Client
```python
import requests

# Query with case context
response = requests.post(
    "http://localhost:8000/api/chat/",
    json={
        "user_query": "What was the plaintiff's main argument?",
        "case_id": 1
    }
)

print(response.json())
```

### cURL
```bash
curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "user_query": "Summarize the key findings",
    "case_id": 1
  }'
```

## Contributing

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Commit changes: `git commit -am 'Add feature'`
3. Push to branch: `git push origin feature/your-feature`
4. Open a pull request

## License

[Your License Here]

## Support

For issues, questions, or suggestions:
1. Check the [OLLAMA_SETUP.md](OLLAMA_SETUP.md) guide
2. Review API documentation
3. Run integration tests: `python test_ollama_integration.py`
4. Check Django logs: `python manage.py runserver --verbosity=3`

## Changelog

### Version 1.0.0
- Initial release
- Ollama integration with llama3.1:8b and nomic-embed-text
- OpenAI fallback support
- Document management and semantic search
- LangGraph-based Q&A workflow
- Citation tracking
- Conversation history
