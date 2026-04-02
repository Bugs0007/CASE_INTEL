# Case Intel - Interview FAQ

> Comprehensive interview preparation guide covering all aspects of the project.
> Last updated: March 2026

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technical Architecture](#2-technical-architecture)
3. [AI/RAG Pipeline](#3-airag-pipeline-deep-dive)
4. [Database Design](#4-database-design)
5. [API Design](#5-api-design)
6. [Frontend Architecture](#6-frontend-architecture)
7. [Design Patterns](#7-design-patterns)
8. [Security & Performance](#8-security--performance)
9. [Deployment & Scalability](#9-deployment--scalability)
10. [Behavioral Questions](#10-behavioral--project-journey)
11. [Code Walkthrough Scenarios](#11-code-walkthrough-scenarios)
12. [Quick Reference Cheatsheet](#12-quick-reference-cheatsheet)

---

## 1. Project Overview

### Q: What is Case Intel? Give me a 60-second elevator pitch.

**Answer:**
Case Intel is an AI-powered legal case management platform that helps legal professionals manage cases, track hearings, and most importantly, **ask questions about their documents in natural language**.

The core value proposition:

- **Problem**: Legal professionals spend 60% of their time searching through documents
- **Solution**: Upload case documents → System extracts text, creates embeddings → Ask questions in plain English → Get answers with source citations

Key features:

- Case & hearing management
- Document upload with automatic processing (PDF, DOCX, TXT)
- Semantic search using vector embeddings (pgvector)
- AI-powered Q&A with LangGraph pipeline
- Gmail integration for case-related emails
- Flexible AI backend (Ollama for privacy, OpenAI for power)

---

### Q: What tech stack did you use and why?

**Answer:**

| Layer                | Technology                                | Why This Choice                                                                                  |
| -------------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------ |
| **Backend**          | Django 6.0.3 + DRF                        | Mature, batteries-included, excellent ORM, rapid development                                     |
| **Database**         | PostgreSQL + pgvector                     | Single database for both relational data AND vector search - simpler ops than separate vector DB |
| **AI Orchestration** | LangGraph                                 | Explicit state machine for complex pipelines, easy to add/modify nodes, built-in error paths     |
| **LLM (Local)**      | Ollama (llama3.1:8b)                      | Free, runs locally, privacy-preserving for sensitive legal documents                             |
| **LLM (Cloud)**      | OpenAI (GPT-4o)                           | Superior quality when privacy isn't the primary concern                                          |
| **Embeddings**       | nomic-embed-text / text-embedding-3-small | High quality semantic representations                                                            |
| **Frontend**         | Next.js 15 + Vanilla JS                   | Next.js for production features, Vanilla JS for rapid prototyping                                |

**Key architectural decision**: Using pgvector instead of Pinecone/Weaviate because:

1. Single database = simpler operations
2. ACID transactions across vector and relational data
3. Django ORM integration
4. Cost-effective for moderate scale

---

### Q: What makes this project unique compared to existing solutions?

**Answer:**

1. **Privacy-first option**: Unlike most AI tools that require cloud APIs, Case Intel can run 100% locally with Ollama - critical for sensitive legal documents

2. **Factory pattern for AI switching**: Single environment variable (`USE_OLLAMA=true/false`) switches the entire AI backend with zero code changes

3. **Citation traceability**: Every AI answer links back to specific document chunks - essential for legal professionals who need to verify sources

4. **LangGraph pipeline with confidence branching**: The system gracefully handles low-confidence scenarios with disclaimers rather than hallucinating

5. **Unified pgvector approach**: Most similar projects use separate vector databases; we kept everything in PostgreSQL for operational simplicity

---

### Q: What was your role in this project?

**Answer:** _(Customize based on your actual role)_

I was the **sole developer / lead developer** responsible for:

- Designing the overall system architecture
- Implementing the Django backend with 16+ models
- Building the LangGraph RAG pipeline from scratch
- Integrating both Ollama and OpenAI as swappable backends
- Creating both frontend implementations (Next.js + Vanilla JS)
- Setting up pgvector for semantic search
- Writing the Gmail OAuth integration
- Documentation and testing

---

## 2. Technical Architecture

### Q: Walk me through the high-level architecture.

**Answer:**

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND LAYER                              │
│   Next.js 15 (React Query, TypeScript)  OR  Vanilla JS SPA         │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ REST API (JSON)
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      DJANGO REST FRAMEWORK                          │
│   /api/cases/  /api/documents/  /api/chat/  /api/hearings/         │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      SERVICE LAYER                                  │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  LangGraph Pipeline                                         │    │
│  │  route → analyze → search → rank → generate → cite → format│    │
│  └────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐    │
│  │ DocumentProcessor│  │ VectorSearch   │  │ AI Factory      │    │
│  │ Extract→Chunk→  │  │ pgvector query │  │ Ollama/OpenAI   │    │
│  │ Embed→Store     │  │ + cosine sim   │  │ routing         │    │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘    │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      DATA LAYER                                     │
│  PostgreSQL + pgvector                                              │
│  ├── cases, hearings, tasks (relational)                           │
│  ├── documents, document_chunks (768-dim vectors)                  │
│  └── conversations, messages, citations (chat history)             │
└─────────────────────────────────────────────────────────────────────┘
```

---

### Q: Explain the request flow when a user asks a question.

**Answer:**

```
User types: "What were the key arguments in the motion to dismiss?"
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. ChatView receives POST /api/chat/                            │
│    - Validates request (query, case_id, conversation_id)       │
│    - Calls AIWorkflowService.process_query()                   │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. AIWorkflowService                                            │
│    - Loads/creates conversation                                 │
│    - Fetches conversation history (last 5 messages)            │
│    - Invokes LangGraph pipeline                                │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. LangGraph Pipeline                                           │
│    a) route_query → Classifies as "analysis" type              │
│    b) analyze_query → Extracts filters: {document_types: motion}│
│    c) vector_search → Embeds query, pgvector cosine search     │
│    d) rank_chunks → LLM reranks top 10 → top 5                 │
│    e) generate_answer → LLM generates answer from chunks       │
│    f) extract_citations → Maps claims to source chunks         │
│    g) format_response → Adds source section                    │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Response returned                                            │
│    {                                                            │
│      "answer": "The motion argued that...",                    │
│      "confidence": 0.87,                                        │
│      "citations": [{document_id, chunk_id, text}],             │
│      "query_type": "analysis"                                  │
│    }                                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

### Q: What are the main Django models and how do they relate?

**Answer:**

**Core Domain (4 models):**

```
Case (central entity)
  ├── Hearing (1:N, CASCADE) - court dates
  ├── Document (1:N, CASCADE) - uploaded files
  ├── Conversation (1:N, CASCADE) - chat sessions
  └── Email (1:N, CASCADE) - synced Gmail messages
```

**AI/RAG (4 models):**

```
Document
  └── DocumentChunk (1:N, CASCADE)
        └── embedding: VectorField(768) ← pgvector

Conversation
  └── Message (1:N, CASCADE)
        └── Citation (1:N, CASCADE)
              └── chunk: FK to DocumentChunk
```

**Supporting (8 models):**

- `Folder` - hierarchical document organization (self-referential)
- `CaseTag`, `DocumentTag` - tagging with explicit mapping tables
- `DocumentVersion` - version history
- `ActivityLog` - audit trail
- `Task` - case-related tasks
- `GmailCredential` - OAuth tokens
- `EmailAttachment` - links emails to documents

**Total: 16 models**

---

### Q: Why did you choose pgvector over Pinecone/Weaviate/Milvus?

**Answer:**

| Factor                 | pgvector                   | Dedicated Vector DB          |
| ---------------------- | -------------------------- | ---------------------------- |
| **Infrastructure**     | Single PostgreSQL instance | Additional service to manage |
| **Transactions**       | ACID with regular data     | Separate consistency model   |
| **Django integration** | Native ORM support         | Custom client needed         |
| **Operational cost**   | Included in existing DB    | Additional hosting cost      |
| **Scale**              | Good up to ~10M vectors    | Better for 100M+ vectors     |
| **Hybrid queries**     | Joins with relational data | Requires separate queries    |

**For Case Intel's scale** (legal firm with thousands of documents, not millions), pgvector is the pragmatic choice. If scaling to enterprise level with billions of vectors, I would consider migrating to a dedicated vector database.

---

## 3. AI/RAG Pipeline (Deep Dive)

### Q: What is RAG and how did you implement it?

**Answer:**

**RAG = Retrieval-Augmented Generation**

Instead of relying solely on the LLM's training data, we:

1. **Retrieve** relevant document chunks using semantic search
2. **Augment** the prompt with these chunks as context
3. **Generate** an answer grounded in the retrieved content

**My implementation:**

```python
# Simplified RAG flow
def process_query(query, case_id):
    # 1. RETRIEVE: Vector search
    query_embedding = embedding_service.embed(query)
    chunks = DocumentChunk.objects.filter(case_id=case_id)\
        .annotate(distance=CosineDistance("embedding", query_embedding))\
        .order_by("distance")[:10]

    # 2. AUGMENT: Build context
    context = "\n\n".join([f"[Doc {i}]: {c.text}" for i, c in enumerate(chunks)])

    # 3. GENERATE: LLM call
    prompt = f"""Answer based ONLY on the following excerpts:
    {context}

    Question: {query}
    """
    answer = llm.generate(prompt)
    return answer
```

---

### Q: Explain your LangGraph pipeline in detail.

**Answer:**

LangGraph is a library for building stateful, multi-step AI pipelines as directed graphs.

**My pipeline has 9 nodes:**

| Node                    | Purpose                       | LLM Call?  |
| ----------------------- | ----------------------------- | ---------- |
| `query_router`          | Classify query type (5 types) | Yes (JSON) |
| `query_analyzer`        | Extract search filters        | Yes (JSON) |
| `vector_search`         | pgvector semantic search      | No         |
| `chunk_ranker`          | LLM reranks + deduplicates    | Yes (JSON) |
| `answer_generator`      | Main response generation      | Yes        |
| `citation_extractor`    | Map claims to chunks          | Yes (JSON) |
| `response_formatter`    | Add source section            | No         |
| `handle_no_results`     | Fallback for empty results    | No         |
| `handle_low_confidence` | Disclaimer + partial answer   | Yes        |

**Flow with branching:**

```
route_query
    │
    ├── (needs_clarification) → END with clarifying question
    │
    └── (proceed) → analyze_query → vector_search
                                        │
                                        ├── (no_results) → handle_no_results → END
                                        │
                                        ├── (low_confidence) → handle_low_confidence → ...
                                        │
                                        └── (good) → rank_chunks → generate_answer →
                                                     extract_citations → format_response → END
```

**Why LangGraph over simple function chain?**

1. Explicit state management via TypedDict
2. Conditional routing based on intermediate results
3. Easy to add new nodes without refactoring
4. Built-in visualization and debugging

---

### Q: What is your chunking strategy and why?

**Answer:**

**Configuration:**

```python
CHUNK_SIZE = 1000 characters
CHUNK_OVERLAP = 200 characters
MAX_CHUNKS_PER_DOCUMENT = 500
```

**Algorithm:**

```python
def chunk_text(text):
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end]

        # Try to break at sentence boundary (last 20% of chunk)
        boundary_zone = chunk[int(CHUNK_SIZE * 0.8):]
        for delimiter in [". ", "? ", "! "]:
            if delimiter in boundary_zone:
                break_point = boundary_zone.rfind(delimiter) + int(CHUNK_SIZE * 0.8) + 2
                chunk = text[start:start + break_point]
                break

        chunks.append(chunk)
        start += len(chunk) - CHUNK_OVERLAP  # Overlap for context continuity

    return chunks
```

**Why these choices?**

- **1000 chars**: Balances context size with embedding quality (too long = diluted semantics)
- **200 overlap**: Ensures ideas spanning chunk boundaries aren't lost
- **Sentence boundaries**: Prevents mid-sentence cuts that harm retrieval quality

---

### Q: How do embeddings work in your system?

**Answer:**

**What are embeddings?**
Dense vector representations of text that capture semantic meaning. Similar texts have similar vectors (close in cosine distance).

**My implementation:**

```python
# Ollama: nomic-embed-text (768 dimensions)
# OpenAI: text-embedding-3-small (1536 dimensions)

class OllamaEmbeddingService:
    def embed(self, text: str) -> list[float]:
        response = self._client.embed(model="nomic-embed-text", input=text)
        return response["embeddings"][0]  # 768-dim vector

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embed(model="nomic-embed-text", input=texts)
        return response["embeddings"]  # Batch API
```

**Storage:**

```python
class DocumentChunk(models.Model):
    embedding = VectorField(dimensions=768, null=True)  # pgvector
```

**Similarity search:**

```python
from pgvector.django import CosineDistance

results = DocumentChunk.objects.annotate(
    distance=CosineDistance("embedding", query_embedding)
).order_by("distance")[:10]

# Convert to similarity: similarity = 1.0 - distance
```

---

### Q: Why two-stage retrieval (search + rerank)?

**Answer:**

**Problem with single-stage:**
Vector search finds semantically similar chunks, but:

- Some irrelevant chunks may have high embedding similarity
- Order may not reflect actual relevance to the specific question

**Solution: Two-stage retrieval**

```
Stage 1: Vector Search (fast, recall-focused)
├── Query embedding → pgvector cosine search
├── Returns top 10 candidates
└── Uses: embedding similarity only

Stage 2: LLM Reranking (slower, precision-focused)
├── LLM reads query + all 10 chunks
├── Scores relevance 0-10 for each
├── Returns top 5 most relevant
└── Uses: semantic understanding + reasoning
```

**Results:** Precision improves from ~70% to ~90% with reranking.

**Implementation:**

```python
def chunk_ranker(state: AgentState, llm) -> AgentState:
    prompt = f"""
    Query: {state['user_query']}

    Score each chunk 0-10 for relevance:
    {format_chunks(state['retrieved_chunks'])}

    Return JSON: [{{"chunk_id": 0, "score": 8}}, ...]
    """
    scores = llm.generate_with_json(prompt)
    ranked = sorted(zip(state['retrieved_chunks'], scores), key=lambda x: x[1], reverse=True)
    return {**state, "retrieved_chunks": ranked[:5]}
```

---

### Q: How do you handle hallucinations?

**Answer:**

**Multiple safeguards:**

1. **Grounding in retrieved content:**

```python
SYSTEM_PROMPT = """
Answer ONLY based on the provided excerpts.
If the information is not in the excerpts, say "I don't have enough information."
NEVER make up facts not present in the sources.
"""
```

2. **Confidence scoring:**

```python
if state['search_confidence'] < 0.5:
    # Route to handle_low_confidence node
    return "low_confidence"
```

3. **Low-confidence disclaimer:**

```python
def handle_low_confidence(state):
    return {
        **state,
        "answer": f"⚠️ Low confidence answer:\n\n{state['answer']}\n\n"
                  f"Note: Limited relevant information found. Please verify."
    }
```

4. **Citation extraction:**
   Every claim is mapped back to source chunks, allowing users to verify.

5. **Empty results fallback:**

```python
def handle_no_results(state):
    return {
        **state,
        "answer": "I couldn't find relevant information in the case documents. "
                  "Try rephrasing your question or adding more documents."
    }
```

---

### Q: How does the AI factory pattern work?

**Answer:**

**Problem:** Need to support both Ollama (free, local, private) and OpenAI (paid, cloud, powerful) without duplicating code.

**Solution:** Factory pattern with identical interfaces.

```python
# ai_service_factory.py

def get_llm_client():
    if settings.USE_OLLAMA:
        return OllamaLLMClient()      # Local llama3.1:8b
    else:
        return LLMClient()            # OpenAI gpt-4o

def get_embedding_service():
    if settings.USE_OLLAMA:
        return OllamaEmbeddingService()  # nomic-embed-text (768d)
    else:
        return EmbeddingService()         # text-embedding-3-small (1536d)
```

**Identical interfaces:**

```python
# Both implement the same methods
class OllamaLLMClient:
    def generate(self, messages, temperature=0.1, max_tokens=4096) -> str
    def generate_with_json(self, messages, ...) -> str

class LLMClient:  # OpenAI
    def generate(self, messages, temperature=0.1, max_tokens=4096) -> str
    def generate_with_json(self, messages, ...) -> str
```

**Usage in services:**

```python
# Consumer doesn't know/care which backend
llm = get_llm_client()
answer = llm.generate(messages)
```

**Switching is one line:**

```bash
# .env
USE_OLLAMA=true   # Use Ollama
USE_OLLAMA=false  # Use OpenAI
```

---

## 4. Database Design

### Q: Explain your DocumentChunk model and pgvector integration.

**Answer:**

```python
class DocumentChunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.IntegerField()  # Order within document
    chunk_text = models.TextField()
    embedding = VectorField(dimensions=768, null=True, blank=True)  # pgvector
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["chunk_index"]
        unique_together = ["document", "chunk_index"]
```

**pgvector features used:**

- `VectorField`: Stores 768-dimensional float vectors
- `CosineDistance`: Similarity search function
- `IvfflatIndex` (optional): For faster search on large datasets

**Why nullable embedding?**
Allows creating chunks first, then generating embeddings asynchronously.

---

### Q: Why CASCADE vs SET_NULL for foreign keys?

**Answer:**

| Relationship           | On Delete    | Reasoning                                    |
| ---------------------- | ------------ | -------------------------------------------- |
| Case → Hearing         | **CASCADE**  | Hearings are meaningless without case        |
| Case → Document        | **CASCADE**  | Documents belong to case lifecycle           |
| Document → Chunk       | **CASCADE**  | Chunks are derived from document             |
| Conversation → Message | **CASCADE**  | Messages belong to conversation              |
| Message → Citation     | **CASCADE**  | Citations are part of response               |
| Folder → Document      | **SET_NULL** | Keep document if folder is reorganized       |
| Document → Citation    | **SET_NULL** | Preserve chat history even if source deleted |
| Email → Citation       | **SET_NULL** | Preserve chat history                        |

**Principle:** CASCADE for strong ownership, SET_NULL for weak references that should survive.

---

### Q: How do you handle embedding dimension differences?

**Answer:**

**Problem:** Ollama uses 768 dimensions, OpenAI uses 1536 dimensions.

**Solution:** Dynamic configuration via settings.

```python
# settings.py
_EMBEDDING_DIMENSIONS_MAP = {
    "nomic-embed-text": 768,        # Ollama
    "text-embedding-3-small": 1536,  # OpenAI
    "text-embedding-3-large": 3072,  # OpenAI large
}

if USE_OLLAMA:
    EMBEDDING_DIMENSIONS = _EMBEDDING_DIMENSIONS_MAP.get(OLLAMA_EMBEDDING_MODEL, 768)
else:
    EMBEDDING_DIMENSIONS = _EMBEDDING_DIMENSIONS_MAP.get(OPENAI_EMBEDDING_MODEL, 1536)
```

**Migration strategy:**
When switching providers, you must:

1. Create new migration changing VectorField dimensions
2. Re-process all documents to regenerate embeddings

```python
# Migration
class Migration(migrations.Migration):
    operations = [
        migrations.AlterField(
            model_name='documentchunk',
            name='embedding',
            field=VectorField(dimensions=1536),  # Changed from 768
        ),
    ]
```

---

## 5. API Design

### Q: How did you design your REST API?

**Answer:**

**Principles followed:**

1. **RESTful resources**: `/api/cases/`, `/api/documents/`
2. **HTTP verbs for actions**: GET (read), POST (create), PATCH (update), DELETE (delete)
3. **Action endpoints for non-CRUD**: `/api/documents/upload/`, `/api/documents/{id}/process/`
4. **Query params for filtering**: `?case_id=1`, `?status=open`, `?upcoming=true`

**Endpoint structure:**

```
/api/
├── dashboard/              GET     (aggregated stats)
├── chat/                   POST    (AI query)
├── cases/                  GET, POST
├── cases/{id}/             GET, PATCH, DELETE
├── hearings/               GET, POST
├── hearings/{id}/          GET, PATCH, DELETE
├── documents/              GET
├── documents/{id}/         GET, DELETE
├── documents/upload/       POST    (multipart)
├── documents/{id}/process/ POST    (trigger processing)
├── conversations/          GET
├── conversations/{id}/     GET, DELETE
├── gmail/auth/             GET     (OAuth start)
├── gmail/callback/         GET     (OAuth callback)
├── gmail/sync/             POST    (fetch emails)
└── emails/                 GET
```

---

### Q: Show me the chat API request/response format.

**Answer:**

**Request:**

```http
POST /api/chat/
Content-Type: application/json

{
  "query": "What were the key arguments in the motion to dismiss?",
  "case_id": 1,
  "conversation_id": null  // null = new conversation
}
```

**Response (success):**

```json
{
  "answer": "Based on the documents, the motion to dismiss argued three key points:\n\n1. **Lack of standing** - The plaintiff failed to demonstrate...\n2. **Statute of limitations** - The claims were filed after...\n3. **Failure to state a claim** - The complaint did not...",
  "confidence": 0.87,
  "query_type": "analysis",
  "requires_clarification": false,
  "clarification_question": null,
  "citations": [
    {
      "document_id": 5,
      "document_name": "motion_to_dismiss.pdf",
      "chunk_id": 12,
      "citation_text": "The defendant respectfully moves to dismiss..."
    },
    {
      "document_id": 5,
      "document_name": "motion_to_dismiss.pdf",
      "chunk_id": 14,
      "citation_text": "Under Rule 12(b)(6), the plaintiff must..."
    }
  ],
  "conversation_id": 3,
  "message_id": 7
}
```

---

### Q: How do you handle file uploads?

**Answer:**

**Two-step process:**

**Step 1: Upload**

```http
POST /api/documents/upload/
Content-Type: multipart/form-data

file: [binary data]
case_id: 1
document_type: "motion"
```

**Response:**

```json
{
  "id": 5,
  "filename": "motion_to_dismiss.pdf",
  "file_type": "pdf",
  "file_size": 1048576,
  "processing_status": "pending",
  "chunk_count": null
}
```

**Step 2: Process**

```http
POST /api/documents/5/process/
```

**Response:**

```json
{
  "id": 5,
  "processing_status": "completed",
  "chunk_count": 23,
  "message": "Document processed successfully"
}
```

**Why two steps?**

1. Upload is quick - user gets immediate feedback
2. Processing can be slow (large PDFs) - allows async handling
3. User can review metadata before processing
4. Enables retry on processing failures

---

## 6. Frontend Architecture

### Q: Why did you build two frontends?

**Answer:**

| Aspect         | Vanilla JS                           | Next.js                         |
| -------------- | ------------------------------------ | ------------------------------- |
| **Purpose**    | Rapid prototyping, simple deployment | Production-ready features       |
| **Size**       | ~50 KB                               | ~200 KB+ (after build)          |
| **Setup**      | Open HTML file directly              | Node.js, npm install            |
| **State**      | Global variables                     | React Query                     |
| **Complexity** | Low (single file)                    | High (components, hooks, types) |

**Use cases:**

- **Vanilla JS**: Quick demos, offline-capable, minimal dependencies
- **Next.js**: Full-featured app with TypeScript, caching, proper state management

---

### Q: Explain your React Query setup in Next.js.

**Answer:**

**Purpose:** Server state management with caching, background refresh, and optimistic updates.

**Configuration:**

```typescript
// providers/query-provider.tsx
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60 * 1000, // 1 minute before refetch
      retry: 1, // Single retry on failure
      refetchOnWindowFocus: false,
    },
  },
});
```

**Query key factory pattern:**

```typescript
// hooks/use-cases.ts
export const caseKeys = {
  all: ["cases"] as const,
  lists: () => [...caseKeys.all, "list"] as const,
  list: (filters: CaseFilters) => [...caseKeys.lists(), filters] as const,
  details: () => [...caseKeys.all, "detail"] as const,
  detail: (id: number) => [...caseKeys.details(), id] as const,
};
```

**Usage:**

```typescript
// Fetch cases with status filter
const { data, isLoading, error } = useQuery({
  queryKey: caseKeys.list({ status: "open" }),
  queryFn: () => casesApi.list({ status: "open" }),
});

// Create case with automatic cache invalidation
const createMutation = useMutation({
  mutationFn: casesApi.create,
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: caseKeys.lists() });
  },
});
```

---

### Q: How does the frontend connect to the Django backend?

**Answer:**

**API client layer:**

```typescript
// lib/api/client.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export async function apiClient<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    throw new APIError(response.status, await response.text());
  }

  return response.json();
}
```

**Type-safe API functions:**

```typescript
// lib/api/cases.ts
export const casesApi = {
  list: (filters?: CaseFilters) =>
    apiClient<Case[]>(`/cases/?${new URLSearchParams(filters)}`),

  get: (id: number) => apiClient<Case>(`/cases/${id}/`),

  create: (data: CreateCaseData) =>
    apiClient<Case>("/cases/", { method: "POST", body: JSON.stringify(data) }),
};
```

**CORS configuration (Django):**

```python
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",  # Next.js dev server
    "http://localhost:8080",  # Vanilla JS
]
```

---

## 7. Design Patterns

### Q: What design patterns did you use?

**Answer:**

1. **Factory Pattern** - AI service selection

```python
def get_llm_client():
    if settings.USE_OLLAMA:
        return OllamaLLMClient()
    return LLMClient()
```

2. **Strategy Pattern** - Swappable embedding providers

```python
class EmbeddingServiceInterface:
    def embed(self, text: str) -> list[float]: ...
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

class OllamaEmbeddingService(EmbeddingServiceInterface): ...
class OpenAIEmbeddingService(EmbeddingServiceInterface): ...
```

3. **State Machine Pattern** - LangGraph pipeline

```python
class AgentState(TypedDict):
    user_query: str
    query_type: str
    retrieved_chunks: list
    answer: str
    # ... state flows through nodes
```

4. **Repository Pattern** - Django ORM as data access layer

```python
DocumentChunk.objects.filter(document__case_id=case_id).annotate(...)
```

5. **Dependency Injection** - Services injected via functools.partial

```python
workflow.add_node("vector_search", partial(vector_search, search_service=search_service))
```

6. **Singleton** - Lazy-initialized AI service in views

```python
_ai_service = None
def get_ai_service():
    global _ai_service
    if _ai_service is None:
        _ai_service = AIWorkflowService()
    return _ai_service
```

---

### Q: How did you implement separation of concerns?

**Answer:**

**Layered architecture:**

```
┌─────────────────────────────────────┐
│ Presentation Layer (Views)          │  ← HTTP handling, validation
├─────────────────────────────────────┤
│ Service Layer                        │  ← Business logic, orchestration
│ ├── AIWorkflowService               │
│ ├── DocumentProcessor               │
│ └── VectorSearchService             │
├─────────────────────────────────────┤
│ Data Access Layer (Models + ORM)    │  ← Database operations
└─────────────────────────────────────┘
```

**Example flow:**

1. **View** validates request, calls service
2. **Service** implements business logic, uses ORM
3. **Model** defines schema, ORM handles SQL

**No business logic in views:**

```python
# views/chat.py
class ChatView(APIView):
    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Delegate to service - view doesn't know about LangGraph, embeddings, etc.
        response = get_ai_service().process_query(
            user_query=serializer.validated_data["query"],
            case_id=serializer.validated_data.get("case_id"),
        )

        return Response(ChatResponseSerializer(response).data)
```

---

## 8. Security & Performance

### Q: How do you handle security in this application?

**Answer:**

**Current implementation:**

1. **Input validation** - DRF serializers validate all input

```python
class DocumentUploadSerializer(serializers.Serializer):
    ALLOWED_EXTENSIONS = {"pdf", "txt", "docx"}
    MAX_SIZE = 50 * 1024 * 1024  # 50 MB

    def validate_file(self, value):
        if value.size > self.MAX_SIZE:
            raise ValidationError("File too large")
        ext = value.name.split(".")[-1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValidationError("Invalid file type")
```

2. **CORS configuration** - Whitelist allowed origins

```python
CORS_ALLOWED_ORIGINS = ["http://localhost:3000", "http://localhost:8080"]
```

3. **SQL injection prevention** - Django ORM parameterizes queries

4. **File storage** - Files stored with collision-resistant names

```python
filename = f"{uuid4()}_{secure_filename(original_name)}"
```

5. **Sensitive data handling** - OAuth tokens encrypted in DB (for Gmail)

**Production recommendations (not yet implemented):**

- User authentication (JWT or session-based)
- Multi-tenancy (filter all queries by user/organization)
- Rate limiting on chat endpoint
- HTTPS enforcement
- Input sanitization for XSS prevention

---

### Q: What performance optimizations did you implement?

**Answer:**

1. **Denormalized `chunk_count`** on Document model

```python
# Avoids COUNT query on every document list
document.chunk_count = len(chunks)
document.save()
```

2. **Batch embedding generation**

```python
# Single API call for multiple texts
embeddings = embedding_service.embed_texts([c.text for c in chunks])
```

3. **Query annotations** to avoid N+1

```python
cases = Case.objects.annotate(
    document_count=Count("documents"),
    hearing_count=Count("hearings")
)
```

4. **Connection pooling** - `CONN_MAX_AGE = 60` in settings

5. **Lazy service initialization**

```python
_ai_service = None  # Created only when first request arrives
```

6. **React Query caching** - 1-minute stale time reduces API calls

7. **Two-stage retrieval** - Fast vector search first, expensive LLM rerank only on top 10

---

### Q: How would you optimize vector search at scale?

**Answer:**

**Current approach (sufficient up to ~1M vectors):**

- Sequential scan with pgvector

**For larger scale:**

1. **IVFFlat index** - Partitions vectors into clusters

```sql
CREATE INDEX ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

2. **HNSW index** - Graph-based approximate search (faster, more RAM)

```sql
CREATE INDEX ON document_chunks USING hnsw (embedding vector_cosine_ops);
```

3. **Filtering optimization** - Use GIN index on metadata fields for combined filters

```sql
CREATE INDEX ON document_chunks USING gin (document_id, case_id);
```

4. **Dedicated vector database** - For 100M+ vectors, consider Pinecone/Weaviate

5. **Embedding caching** - Cache query embeddings (e.g., Redis) for repeated queries

---

## 9. Deployment & Scalability

### Q: How would you deploy this to production?

**Answer:**

**Recommended architecture:**

```
┌─────────────────────────────────────────────────────────────────┐
│                          Load Balancer                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│  Django App   │  │  Django App   │  │  Django App   │
│  (Gunicorn)   │  │  (Gunicorn)   │  │  (Gunicorn)   │
└───────┬───────┘  └───────┬───────┘  └───────┬───────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────────┐
        │        PostgreSQL (pgvector)             │
        │        - Primary + Read Replica          │
        └──────────────────────────────────────────┘
                           │
                           │
        ┌──────────────────┴──────────────────┐
        │                                     │
        ▼                                     ▼
┌───────────────┐                   ┌───────────────┐
│    Redis      │                   │ Celery Worker │
│ (cache/queue) │                   │ (document     │
└───────────────┘                   │  processing)  │
                                    └───────────────┘
```

**Components:**

- **Gunicorn**: WSGI server (4-8 workers per instance)
- **Nginx**: Static files, reverse proxy
- **Celery**: Async document processing
- **Redis**: Task queue + optional caching
- **PostgreSQL**: Primary with read replica for analytics

**Docker Compose example:**

```yaml
services:
  web:
    build: .
    command: gunicorn case_intel_project.wsgi:application -w 4 -b 0.0.0.0:8000

  db:
    image: pgvector/pgvector:pg15

  redis:
    image: redis:alpine

  celery:
    build: .
    command: celery -A case_intel_project worker -l info
```

---

### Q: How would you scale for 1000 concurrent users?

**Answer:**

**Bottleneck analysis:**

1. **LLM calls** - Each query makes 4-5 LLM calls
   - Solution: Use OpenAI (handles scale), or multiple Ollama instances

2. **Embedding generation** - CPU-intensive for document processing
   - Solution: Async Celery workers, batch processing

3. **Vector search** - pgvector sequential scan slows at scale
   - Solution: IVFFlat/HNSW indexes, or dedicated vector DB

4. **Database connections** - Exhausted under load
   - Solution: PgBouncer connection pooling

**Scaling strategy:**

| Component           | Strategy                                    |
| ------------------- | ------------------------------------------- |
| Django              | Horizontal: multiple Gunicorn instances     |
| Document Processing | Async Celery with autoscaling workers       |
| Vector Search       | pgvector with HNSW index, partition by case |
| LLM                 | OpenAI (unlimited scale) or Ollama cluster  |
| Database            | Read replicas, connection pooling           |
| Frontend            | CDN for static assets                       |

**Approximate costs (AWS):**

- 2x c5.xlarge (Django): ~$250/mo
- db.r5.xlarge (PostgreSQL): ~$300/mo
- ElastiCache (Redis): ~$50/mo
- OpenAI API: Variable ($10-1000+/mo based on usage)

---

## 10. Behavioral / Project Journey

### Q: What was the most challenging part of this project?

**Answer:**

The **LangGraph pipeline design** was the most challenging because:

1. **State management complexity**: Figuring out what state to pass between nodes without coupling them tightly

2. **Conditional routing**: Designing the branching logic (clarification needed? no results? low confidence?) required thinking through all edge cases

3. **Prompt engineering**: Each node required careful prompt crafting - especially the citation extractor which needs to map claims to specific chunks

4. **Testing**: Unit testing stateless nodes with mocked dependencies required designing for dependency injection

**How I solved it:**

- Drew the pipeline flow on paper first
- Implemented nodes as pure functions with injected dependencies
- Used TypedDict for explicit state contracts
- Added extensive logging to trace state flow

---

### Q: What would you do differently if starting over?

**Answer:**

1. **Add authentication from day one** - Currently no auth; retrofitting is harder than building it in

2. **Use Celery for document processing** - Currently synchronous; large PDFs block the request

3. **Implement streaming responses** - Users wait for full LLM generation; streaming would improve UX

4. **Add comprehensive tests earlier** - Test coverage is limited; should have started with TDD for services

5. **Consider hybrid search** - Combine keyword search (BM25) with vector search for better results

---

### Q: What did you learn from this project?

**Answer:**

1. **RAG pipeline nuances**: Two-stage retrieval (search + rerank) significantly improves precision

2. **pgvector capabilities**: Surprisingly powerful - can handle moderate scale without dedicated vector DB

3. **LangGraph patterns**: State machine approach makes complex AI workflows maintainable

4. **Factory pattern value**: Single env var switching between AI providers saved massive refactoring

5. **Chunking matters**: Sentence-boundary-aware chunking with overlap is crucial for retrieval quality

6. **Prompt engineering is iterative**: Each LLM node required multiple iterations to get right

---

### Q: How would you improve this project in the future?

**Answer:**

**Short-term (1-2 sprints):**

- [ ] User authentication + multi-tenancy
- [ ] Celery for async document processing
- [ ] Streaming LLM responses (SSE)
- [ ] Unit tests for services

**Medium-term (1-2 months):**

- [ ] Hybrid search (BM25 + vector)
- [ ] OCR for scanned documents
- [ ] Advanced analytics dashboard
- [ ] Document comparison feature

**Long-term (3+ months):**

- [ ] Mobile app (React Native)
- [ ] Multi-language support
- [ ] Custom model fine-tuning
- [ ] Integration with legal research APIs (Westlaw, LexisNexis)

---

## 11. Code Walkthrough Scenarios

### Q: Walk me through adding a new document type (e.g., Excel).

**Answer:**

1. **Update serializer validation:**

```python
# core/serializers/document.py
ALLOWED_UPLOAD_EXTENSIONS = {"pdf", "txt", "docx", "xlsx", "xls"}
```

2. **Add extraction logic:**

```python
# core/services/document_processor.py
import openpyxl

def _extract_text(self, file_path: str, file_type: str) -> str:
    if file_type in ("xlsx", "xls"):
        return self._extract_excel(file_path)
    # ... existing logic

def _extract_excel(self, file_path: str) -> str:
    wb = openpyxl.load_workbook(file_path)
    text_parts = []
    for sheet in wb.worksheets:
        for row in sheet.iter_rows(values_only=True):
            text_parts.append(" ".join(str(cell) for cell in row if cell))
    return "\n".join(text_parts)
```

3. **Add dependency:**

```
# requirements.txt
openpyxl>=3.1.0
```

4. **Test:**

- Upload Excel file
- Process document
- Verify chunks created
- Test search against content

---

### Q: Walk me through adding a new query type to the pipeline.

**Answer:**

Example: Adding "timeline" query type to generate chronological summaries.

1. **Update query types in router:**

```python
# core/services/graph/nodes.py
QUERY_TYPES = ["simple_qa", "summarize", "compare", "timeline", "unclear"]

# Update router prompt to recognize timeline queries
```

2. **Add new node if needed:**

```python
def timeline_generator(state: AgentState, llm) -> AgentState:
    """Generate chronological timeline from chunks."""
    prompt = f"""
    Create a chronological timeline from these excerpts:
    {format_chunks(state['retrieved_chunks'])}

    Format as: DATE: EVENT
    """
    timeline = llm.generate(prompt)
    return {**state, "answer": timeline}
```

3. **Update builder routing:**

```python
# core/services/graph/builder.py
def _route_by_query_type(state: AgentState) -> str:
    if state["query_type"] == "timeline":
        return "timeline"
    # ... existing routing

workflow.add_conditional_edges("analyze_query", _route_by_query_type, {
    "timeline": "timeline_generator",
    # ...
})
```

---

## 12. Quick Reference Cheatsheet

### Project Stats

- **Models**: 16
- **API Endpoints**: 20+
- **LangGraph Nodes**: 9
- **Lines of Code**: ~5000 (Python), ~2000 (TypeScript/JS)

### Key Files

| Purpose            | Path                                     |
| ------------------ | ---------------------------------------- |
| Django settings    | `case_intel_project/settings.py`         |
| All models         | `core/models/__init__.py`                |
| LangGraph pipeline | `core/services/graph/`                   |
| AI factory         | `core/services/ai_service_factory.py`    |
| Document processor | `core/services/document_processor.py`    |
| Vector search      | `core/services/vector_search_service.py` |
| Chat view          | `core/views/chat.py`                     |
| Next.js hooks      | `frontend-next/hooks/`                   |

### Key Commands

```bash
# Start Django
python manage.py runserver

# Start Ollama
ollama serve

# Start Next.js
cd frontend-next && npm run dev

# Run migrations
python manage.py migrate

# Test Ollama integration
python test_ollama_integration.py
```

### Environment Variables

```bash
USE_OLLAMA=true                    # Toggle AI backend
OLLAMA_MODEL=llama3.1:8b           # Ollama model
OPENAI_API_KEY=sk-...              # OpenAI key
DB_NAME=case_intel                 # Database
AI_SEARCH_TOP_K=10                 # Vector search results
AI_CONFIDENCE_THRESHOLD=0.5        # Confidence cutoff
```

### Query Flow Summary

```
User Query → ChatView → AIWorkflowService → LangGraph Pipeline
    ↓
route_query → analyze_query → vector_search → rank_chunks
    ↓
generate_answer → extract_citations → format_response
    ↓
Response with answer + confidence + citations
```

---

**Good luck with your interview! You've got this!**
