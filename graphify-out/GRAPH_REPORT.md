# Graph Report - C:\Users\Bhagath\OneDrive\Desktop\CASE_INTEL  (2026-05-06)

## Corpus Check
- 168 files · ~79,050 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 692 nodes · 1040 edges · 74 communities (37 shown, 37 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 111 edges (avg confidence: 0.71)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]

## God Nodes (most connected - your core abstractions)
1. `DocumentProcessor` - 21 edges
2. `GmailService` - 19 edges
3. `_make_state()` - 17 edges
4. `AgentState` - 15 edges
5. `cn()` - 13 edges
6. `apiClient()` - 12 edges
7. `OllamaLLMClient` - 11 edges
8. `TestTextChunking` - 11 edges
9. `Card()` - 11 edges
10. `CardContent()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `test_factory_pattern()` --calls--> `get_llm_client()`  [INFERRED]
  test_ollama_integration.py → core/services/ai_service_factory.py
- `test_factory_pattern()` --calls--> `get_embedding_service()`  [INFERRED]
  test_ollama_integration.py → core/services/ai_service_factory.py
- `migrate_all_documents()` --calls--> `get_embedding_service()`  [INFERRED]
  scripts/migrate_to_ollama.py → core/services/ai_service_factory.py
- `test_ollama_connection()` --calls--> `OllamaLLMClient`  [INFERRED]
  test_ollama_integration.py → core/services/ollama_llm_client.py
- `test_embedding_generation()` --calls--> `OllamaEmbeddingService`  [INFERRED]
  test_ollama_integration.py → core/services/ollama_embedding_service.py

## Communities (74 total, 37 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (52): answer_generator(), _build_context(), chunk_ranker(), citation_extractor(), handle_low_confidence(), handle_no_results(), _parse_json_safe(), query_analyzer() (+44 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (21): CaseFilters(), handleSubmit(), validateForm(), cn(), handleKeyPress(), handleSend(), DashboardPage(), QuickActions() (+13 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (36): get_migration_status(), migrate_all_documents(), migrate_document(), Migration script from OpenAI embeddings to Ollama embeddings.  This script re-, Rollback: Re-process all documents with OpenAI embeddings.      Only works if, Get migration status information., Re-process a single document with new embeddings.      Args:         document, Migrate all documents to new embeddings.      This will:     1. Load each doc (+28 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (35): APIView, GmailService, Gmail API integration service.  Handles OAuth flow, email sync, and attachment, Sync emails from Gmail to local database., Service for Gmail API operations., Extract text body from email payload., Check if email has attachments., Download and store email attachments. (+27 more)

### Community 4 - "Community 4"
Cohesion: 0.05
Nodes (20): apiClient(), uploadFile(), AIResponse, _get_or_create_conversation(), _load_conversation_history(), process_query(), AI Workflow orchestrator for the Case Intel application.  This module is the p, Immutable result returned from the AI workflow. (+12 more)

### Community 5 - "Community 5"
Cohesion: 0.05
Nodes (24): get_embedding_service(), get_llm_client(), Factory module for AI service instantiation.  Provides a centralized way to cr, Factory function to create an LLM client.      Returns:         LLMClient or, Factory function to create an embedding service.      Returns:         Embedd, AIWorkflowService, Orchestrates the LangGraph pipeline and persists results.      This service is, EmbeddingService (+16 more)

### Community 6 - "Community 6"
Cohesion: 0.07
Nodes (28): Integration tests for Ollama LLM and embedding services.  This standalone scri, Test LLM text generation., Test LLM JSON generation., Test the AI service factory., Run all integration tests., Test connection to Ollama server., Test embedding generation., Test batch embedding generation. (+20 more)

### Community 7 - "Community 7"
Cohesion: 0.09
Nodes (15): APIError, DocumentFilters(), EditDocumentDialog(), handleDrop(), handleFileChange(), handleFileSelect(), validateFile(), useCases() (+7 more)

### Community 8 - "Community 8"
Cohesion: 0.09
Nodes (19): CaseSerializer, Meta, Serializers for legal cases., ChatRequestSerializer, ChatResponseSerializer, CitationSerializer, MessageSerializer, Meta (+11 more)

### Community 9 - "Community 9"
Cohesion: 0.09
Nodes (19): ActivityLogAdmin, CaseAdmin, CaseTagAdmin, CaseTagMapAdmin, CitationAdmin, ConversationAdmin, DocumentAdmin, DocumentChunkAdmin (+11 more)

### Community 10 - "Community 10"
Cohesion: 0.14
Nodes (10): build_legal_ai_graph(), _check_results(), LangGraph graph builder for the Case Intel AI workflow.  Constructs the comple, Route after query_router: clarify or proceed to analysis., Route after vector_search based on result quality., Build and compile the LangGraph workflow.      Uses functools.partial to injec, _should_clarify(), Unit tests for the LangGraph builder.  Verifies that the graph compiles succes (+2 more)

### Community 11 - "Community 11"
Cohesion: 0.2
Nodes (10): DocumentChunk, Meta, _extract_docx(), _extract_pdf(), extract_text_from_file(), _extract_txt(), _find_sentence_boundary(), process_document() (+2 more)

### Community 12 - "Community 12"
Cohesion: 0.29
Nodes (5): SyncConfigCard(), useEmails(), useLinkEmail(), useGmailStatus(), useSyncEmails()

### Community 13 - "Community 13"
Cohesion: 0.25
Nodes (6): FolderSerializer, Meta, Serializers for folders., FolderListView, Folder views — list folders for document organization., List all folders.          GET /api/folders/

### Community 15 - "Community 15"
Cohesion: 0.33
Nodes (6): ChunkData, CitationData, LangGraph state schema for the Case Intel AI workflow.  Defines the typed stat, Serialized representation of a retrieved document chunk., A citation linking an answer claim to a source chunk., TypedDict

### Community 16 - "Community 16"
Cohesion: 0.29
Nodes (5): HearingDetailView, HearingListCreateView, Hearing views — CRUD operations on case hearings., List or create hearings.      GET  /api/hearings/     GET  /api/hearings/?cas, Retrieve, update, or delete a hearing.      GET    /api/hearings/<id>/     PA

### Community 17 - "Community 17"
Cohesion: 0.29
Nodes (5): ConversationDetailView, ConversationListView, Conversation views — list, retrieve, and delete conversations., List conversations, optionally filtered by case_id.      GET /api/conversation, Retrieve or delete a conversation with its messages.      GET    /api/conversa

### Community 18 - "Community 18"
Cohesion: 0.33
Nodes (4): debug_task(), Celery configuration for Case Intel project, Debug task to test Celery configuration, This will make sure the app is always imported when Django starts so that shared

### Community 19 - "Community 19"
Cohesion: 0.33
Nodes (4): GmailCredential, Meta, Gmail OAuth credential storage., Stores Gmail OAuth tokens.

### Community 20 - "Community 20"
Cohesion: 0.33
Nodes (3): CaseTag, CaseTagMap, Meta

### Community 21 - "Community 21"
Cohesion: 0.33
Nodes (3): DocumentTag, DocumentTagMap, Meta

## Knowledge Gaps
- **207 isolated node(s):** `Run administrative tasks.`, `Integration tests for Ollama LLM and embedding services.  This standalone scri`, `Test connection to Ollama server.`, `Test embedding generation.`, `Test batch embedding generation.` (+202 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **37 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `DocumentProcessor` connect `Community 2` to `Community 11`, `Community 5`?**
  _High betweenness centrality (0.201) - this node is a cross-community bridge._
- **Why does `AIResponse` connect `Community 4` to `Community 0`, `Community 5`?**
  _High betweenness centrality (0.183) - this node is a cross-community bridge._
- **Are the 16 inferred relationships involving `DocumentProcessor` (e.g. with `TestTextChunking` and `TestDocumentProcessing`) actually correct?**
  _`DocumentProcessor` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `GmailService` (e.g. with `GmailAuthView` and `GmailCallbackView`) actually correct?**
  _`GmailService` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `AgentState` (e.g. with `AIResponse` and `AIWorkflowService`) actually correct?**
  _`AgentState` has 12 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Run administrative tasks.`, `Integration tests for Ollama LLM and embedding services.  This standalone scri`, `Test connection to Ollama server.` to the rest of the system?**
  _207 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.05 - nodes in this community are weakly interconnected._