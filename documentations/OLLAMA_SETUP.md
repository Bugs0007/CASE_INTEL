# Ollama Integration Setup Guide

This guide explains how to set up and use Case Intel with Ollama for 100% local AI processing without OpenAI API costs.

## Overview

Case Intel supports two AI backends:

- **OpenAI** (default): Cloud-based, GPT-4o + text-embedding-3-small
- **Ollama** (recommended for privacy): Local, llama3.1:8b + nomic-embed-text

The system uses a factory pattern to switch between backends with a single environment variable.

## Prerequisites

### System Requirements

- **RAM**: Minimum 8GB, recommended 16GB
- **Disk**: ~10GB for models
- **OS**: Windows, Mac, or Linux
- **Python**: 3.12+
- **PostgreSQL**: 15+ with pgvector extension

### Install Ollama

1. **Download Ollama**
   - Visit [ollama.ai](https://ollama.ai)
   - Download the installer for your OS
   - Run the installer and follow the prompts

2. **Verify Installation**

   ```bash
   ollama --version
   ```

3. **Download Required Models**

   ```bash
   # LLM for text generation
   ollama pull llama3.1:8b

   # Embedding model for semantic search (768 dimensions)
   ollama pull nomic-embed-text
   ```

   Note: Models will be downloaded locally to `~/.ollama/models/`

4. **Start Ollama Server**

   ```bash
   ollama serve
   ```

   The server will run on `http://localhost:11434` by default.
   Keep this terminal open while using Case Intel.

## Configuration

### Step 1: Update Environment Variables

Edit `.env` file in the project root:

```bash
# ============================================================================
# AI Provider Toggle
# ============================================================================
USE_OLLAMA=true

# ============================================================================
# Ollama Configuration
# ============================================================================
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

### Step 2: Verify Database Schema

The embedding dimension changes from 1536 (OpenAI) to 768 (Ollama):

```bash
# Apply migration
python manage.py migrate
```

### Step 3: Migrate Existing Embeddings (Optional)

If you have existing documents with OpenAI embeddings:

```bash
# From Django shell
python manage.py shell
>>> from scripts.migrate_to_ollama import migrate_all_documents
>>> migrate_all_documents()
```

Or in one command:

```bash
python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'case_intel_project.settings')
django.setup()
from scripts.migrate_to_ollama import migrate_all_documents
migrate_all_documents()
"
```

This will re-process all documents with new Ollama embeddings.

## Testing

### Run Integration Tests

```bash
python test_ollama_integration.py
```

This script tests:

- ✓ Ollama server connection
- ✓ Embedding generation (single and batch)
- ✓ LLM text generation
- ✓ JSON response generation
- ✓ Factory pattern routing

Expected output:

```
╔════════════════════════════════════════════════════════════════════╗
║               OLLAMA INTEGRATION TEST SUITE                         ║
╚════════════════════════════════════════════════════════════════════╝

[✓ PASS] Connection
[✓ PASS] Embedding Single
[✓ PASS] Embedding Batch
[✓ PASS] LLM Generation
[✓ PASS] JSON Generation
[✓ PASS] Factory Pattern
```

### Manual Testing

Start the Django server:

```bash
python manage.py runserver
```

Test the API:

```bash
curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "user_query": "What is a motion to dismiss?",
    "case_id": 1
  }'
```

## Model Selection

### Recommended Models

**LLM Models** (text generation):

- `llama3.1:8b` - Recommended, good balance of speed and quality
- `llama3.1:70b` - Better quality, but slower, requires more VRAM
- `mistral:7b` - Faster, good for quick responses
- `neural-chat:7b` - Optimized for chat

**Embedding Models** (semantic search):

- `nomic-embed-text` - **Recommended**, 768 dimensions, fast and accurate
- `mxbai-embed-large` - 1024 dimensions, slightly better quality
- `all-minilm` - 384 dimensions, very fast but lower quality

To use different models:

1. Download the model:

   ```bash
   ollama pull mistral:7b
   ```

2. Update `.env`:

   ```bash
   OLLAMA_MODEL=mistral:7b
   OLLAMA_EMBEDDING_MODEL=mxbai-embed-large
   ```

3. **Update database schema** if changing embedding dimensions:
   - Edit `core/models/document_chunk.py` and update the VectorField dimensions
   - Create and apply migration: `python manage.py migrate`
   - Re-process documents with new embeddings

## Architecture Changes

### Service Layer

The integration uses a factory pattern (`core/services/ai_service_factory.py`):

```python
from core.services.ai_service_factory import get_llm_client, get_embedding_service

# Returns OllamaLLMClient or LLMClient based on USE_OLLAMA setting
llm = get_llm_client()

# Returns OllamaEmbeddingService or EmbeddingService
embeddings = get_embedding_service()
```

### New Files

- `core/services/ollama_llm_client.py` - Ollama chat interface
- `core/services/ollama_embedding_service.py` - Ollama embeddings
- `core/services/ai_service_factory.py` - Factory for service selection

### Modified Files

- `case_intel_project/settings.py` - Added Ollama configuration
- `core/models/document_chunk.py` - Changed embedding dimensions to 768
- `core/services/ai_workflow.py` - Uses factory pattern
- `core/services/document_processor.py` - Uses factory pattern
- `core/services/vector_search_service.py` - Uses factory pattern

### Database Migration

Migration `0002_alter_documentchunk_embedding`:

- Changes embedding field from 1536 to 768 dimensions
- Automatically generated: `python manage.py makemigrations core`

## Performance

### Expected Performance

| Operation            | Model            | Time               |
| -------------------- | ---------------- | ------------------ |
| Embedding 1 text     | nomic-embed-text | ~100ms             |
| Embedding batch (10) | nomic-embed-text | ~200ms             |
| LLM response         | llama3.1:8b      | 50-200ms per token |
| Vector search        | pgvector         | <100ms             |

**Note**: First request takes longer as models are loaded into VRAM.

### Optimization Tips

1. **Keep Ollama running** in the background to avoid model reload time
2. **Adjust batch size** in `DocumentProcessor` for faster processing
3. **Use GPU acceleration** if available (Ollama auto-detects):
   - NVIDIA: CUDA support (requires CUDA toolkit)
   - Apple: Metal support (automatic)
   - AMD: ROCm support (requires ROCm installation)
4. **Monitor VRAM usage** with `nvidia-smi` for NVIDIA GPUs

## Troubleshooting

### Error: "Cannot connect to Ollama at http://localhost:11434"

**Solution:**

1. Ensure Ollama is running: `ollama serve`
2. Check the port is correct in `.env` (default: 11434)
3. Check firewall settings
4. Test connection: `curl http://localhost:11434/api/tags`

### Error: "Model not found: llama3.1:8b"

**Solution:**

1. Download the model: `ollama pull llama3.1:8b`
2. List available models: `ollama list`
3. Check model name spelling in `.env`

### Error: "Embedding dimension mismatch: expected 768, got 1536"

**Solution:**

1. You likely switched from OpenAI (1536) to Ollama (768)
2. Update database schema:
   ```bash
   python manage.py makemigrations core
   python manage.py migrate
   ```
3. Re-process documents:
   ```bash
   python -c "
   import django, os
   os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'case_intel_project.settings')
   django.setup()
   from scripts.migrate_to_ollama import migrate_all_documents
   migrate_all_documents()
   "
   ```

### Error: "Out of memory" or slow responses

**Solution:**

1. **Reduce model size**: Use `mistral:7b` instead of `llama3.1:70b`
2. **Increase system swap**: Allows spilling to disk
3. **Close other applications**: Free up VRAM
4. **Use GPU acceleration**: Offload processing from CPU

### Error: "JSON parsing failed"

**Solution:**

1. Llama models sometimes struggle with JSON mode
2. The system has a fallback parser for partial JSON
3. Try increasing `temperature` to 0.0 for deterministic output
4. Consider using `mistral:7b` for better JSON compliance

## Switching Back to OpenAI

To revert to OpenAI:

1. **Update `.env`:**

   ```bash
   USE_OLLAMA=false
   ```

2. **Update database schema** (if you want OpenAI embeddings):
   - Edit `core/models/document_chunk.py`: change `dimensions=768` to `dimensions=1536`
   - Run migration: `python manage.py migrate`

3. **Re-process documents** with OpenAI embeddings:
   ```bash
   python -c "
   import django, os
   os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'case_intel_project.settings')
   django.setup()
   from scripts.migrate_to_ollama import migrate_all_documents
   migrate_all_documents()
   "
   ```

## Additional Resources

- [Ollama Documentation](https://github.com/ollama/ollama)
- [Available Models](https://ollama.ai/library)
- [pgvector](https://github.com/pgvector/pgvector)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)

## FAQ

**Q: Will Ollama work offline?**
A: Yes! Once models are downloaded, Ollama works completely offline. No internet connection required.

**Q: Can I use different LLM and embedding models?**
A: Yes! Download any supported Ollama model and update `OLLAMA_MODEL` and `OLLAMA_EMBEDDING_MODEL` in `.env`. Note: Embedding model dimensions must match the database schema.

**Q: What's the quality difference between Ollama and OpenAI?**
A: llama3.1:8b is very good but slightly worse than GPT-4o. For most legal document analysis, it's more than sufficient and significantly faster locally.

**Q: How much disk space do I need?**
A:

- llama3.1:8b: ~4.7GB
- mistral:7b: ~4GB
- nomic-embed-text: ~274MB
- Total with both: ~9GB

**Q: Can I run this on a Mac?**
A: Yes! Ollama automatically uses Metal acceleration on Mac. Performance is good for most operations.

**Q: How do I update Ollama or models?**
A: ```bash
ollama pull llama3.1:8b # Updates to latest version

```

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Run `test_ollama_integration.py` to diagnose problems
3. Check logs: `DJANGO_DEBUG=True python manage.py runserver`
4. Open an issue on the project repository
```
