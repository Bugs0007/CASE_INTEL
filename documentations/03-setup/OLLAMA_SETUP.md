# Ollama Setup

This guide reflects the models and settings currently used by the repo.

## Verified Default Models

Configured in `.env.example` and `settings.py`:

- chat model: `llama3.1:8b`
- embedding model: `nomic-embed-text`

Verified locally on this machine with `ollama list` on July 4, 2026:

- `llama3.1:8b`
- `nomic-embed-text`
- `qwen:7b` also installed locally, but not referenced by current settings

## 1. Install and Start Ollama

```powershell
ollama serve
```

## 2. Pull Required Models

```powershell
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

## 3. Configure `.env`

Use the Ollama defaults:

```env
USE_OLLAMA=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

## 4. Verify the Repo Matches the Model Choice

- `settings.py` maps `nomic-embed-text` to `768` dimensions
- `core/models/document_chunk.py` stores vectors in `VectorField(dimensions=768)`
- `core/services/ollama_llm_client.py` is the active chat client when `USE_OLLAMA=true`
- `core/services/ollama_embedding_service.py` is the active embedding client when `USE_OLLAMA=true`

## 5. Run the App

Backend:

```powershell
.\.venv\Scripts\python.exe manage.py runserver 8000
```

Frontend:

```powershell
cd frontend-next
npm run dev
```

## 6. Troubleshooting

### `Cannot connect to Ollama server`

- start `ollama serve`
- confirm `OLLAMA_BASE_URL` matches the running host

### `Model not found`

Pull the missing model:

```powershell
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

### Embedding dimension mismatch

The current schema expects 768-dimensional vectors. If you switch to a different embedding model, update the model code and migration strategy together before re-embedding data.

## OpenAI Fallback

OpenAI support still exists through:

- `core/services/llm_client.py`
- `core/services/embedding_service.py`
- `core/services/ai_service_factory.py`

Use it by setting:

```env
USE_OLLAMA=false
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

That code path exists, but this documentation pass did not verify it end-to-end in the local environment.
