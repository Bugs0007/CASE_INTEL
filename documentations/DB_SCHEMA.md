# Case Intel - Database Schema Documentation

**Last Updated:** March 2026
**Database:** PostgreSQL with pgvector extension
**ORM:** Django 6.0.3

---

## Overview

The Case Intel database consists of **17 tables** organized into the following domains:

| Domain       | Tables                                                                        | Purpose                            |
| ------------ | ----------------------------------------------------------------------------- | ---------------------------------- |
| Core         | Case, Hearing, Task                                                           | Legal case management              |
| Documents    | Document, DocumentChunk, Folder, DocumentTag, DocumentTagMap, DocumentVersion | Document storage and AI processing |
| Chat/AI      | Conversation, Message, Citation                                               | AI Q&A with source tracking        |
| Email        | Email, EmailAttachment, GmailCredential                                       | Gmail integration                  |
| Organization | CaseTag, CaseTagMap, ActivityLog                                              | Tagging and audit                  |

---

## Entity Relationship Diagram (Simplified)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CASE (Core Entity)                             │
│  id | case_number | title | client_name | status | priority | case_type    │
└─────────────────────────────────────────────────────────────────────────────┘
         │              │              │              │              │
         │ 1:N          │ 1:N          │ 1:N          │ 1:N          │ 1:N
         ▼              ▼              ▼              ▼              ▼
    ┌─────────┐   ┌──────────┐   ┌─────────┐   ┌───────────┐   ┌─────────┐
    │ Hearing │   │ Document │   │ Email   │   │Conversation│   │  Task   │
    └─────────┘   └──────────┘   └─────────┘   └───────────┘   └─────────┘
                       │                              │
                       │ 1:N                          │ 1:N
                       ▼                              ▼
                 ┌───────────────┐              ┌─────────┐
                 │ DocumentChunk │              │ Message │
                 │  (pgvector)   │              └─────────┘
                 └───────────────┘                   │
                                                     │ 1:N
                                                     ▼
                                               ┌──────────┐
                                               │ Citation │
                                               └──────────┘
```

---

## Table Definitions

### 1. Case (`cases`)

**Purpose:** Core entity representing a legal case.

| Column           | Type         | Constraints      | Default  | Description                           |
| ---------------- | ------------ | ---------------- | -------- | ------------------------------------- |
| `id`             | SERIAL       | PRIMARY KEY      | auto     | Unique identifier                     |
| `case_number`    | VARCHAR(100) | UNIQUE, NOT NULL | -        | Case identifier (e.g., "2024-CV-001") |
| `title`          | VARCHAR(500) | NOT NULL         | -        | Case title                            |
| `client_name`    | VARCHAR(255) | NOT NULL         | -        | Client's name                         |
| `opposing_party` | VARCHAR(255) | NULL             | -        | Opposing party name                   |
| `case_type`      | VARCHAR(50)  | NOT NULL         | -        | Type classification                   |
| `status`         | VARCHAR(20)  | NOT NULL         | 'open'   | Current status                        |
| `priority`       | VARCHAR(20)  | NOT NULL         | 'medium' | Priority level                        |
| `filing_date`    | DATE         | NULL             | -        | Date case was filed                   |
| `notes`          | TEXT         | NULL             | -        | Additional notes                      |
| `created_at`     | TIMESTAMP    | NOT NULL         | NOW()    | Creation timestamp                    |

**Choices:**

```python
CASE_TYPE_CHOICES = [
    ('civil', 'Civil'),
    ('criminal', 'Criminal'),
    ('family', 'Family'),
    ('corporate', 'Corporate'),
    ('ip', 'Intellectual Property'),
    ('labor', 'Labor'),
    ('tax', 'Tax'),
    ('other', 'Other'),
]

STATUS_CHOICES = [
    ('open', 'Open'),
    ('closed', 'Closed'),
    ('pending', 'Pending'),
    ('archived', 'Archived'),
]

PRIORITY_CHOICES = [
    ('low', 'Low'),
    ('medium', 'Medium'),
    ('high', 'High'),
    ('critical', 'Critical'),
]
```

**Indexes:**

- `cases_case_number_key` (UNIQUE on case_number)
- `cases_status_idx` (on status)
- `cases_priority_idx` (on priority)

---

### 2. Hearing (`hearings`)

**Purpose:** Court hearings associated with a case.

| Column         | Type         | Constraints                      | Default     | Description          |
| -------------- | ------------ | -------------------------------- | ----------- | -------------------- |
| `id`           | SERIAL       | PRIMARY KEY                      | auto        | Unique identifier    |
| `case_id`      | INTEGER      | FK → cases(id) ON DELETE CASCADE | -           | Related case         |
| `hearing_date` | TIMESTAMP    | NOT NULL                         | -           | Date/time of hearing |
| `hearing_type` | VARCHAR(50)  | NOT NULL                         | -           | Type of hearing      |
| `location`     | VARCHAR(255) | NULL                             | -           | Court location       |
| `judge`        | VARCHAR(255) | NULL                             | -           | Presiding judge      |
| `status`       | VARCHAR(20)  | NOT NULL                         | 'scheduled' | Hearing status       |
| `notes`        | TEXT         | NULL                             | -           | Pre-hearing notes    |
| `outcome`      | TEXT         | NULL                             | -           | Post-hearing outcome |
| `created_at`   | TIMESTAMP    | NOT NULL                         | NOW()       | Creation timestamp   |
| `updated_at`   | TIMESTAMP    | NOT NULL                         | NOW()       | Last update          |

**Choices:**

```python
HEARING_TYPE_CHOICES = [
    ('preliminary', 'Preliminary Hearing'),
    ('motion', 'Motion Hearing'),
    ('trial', 'Trial'),
    ('appeal', 'Appeal'),
    ('sentencing', 'Sentencing'),
    ('arraignment', 'Arraignment'),
    ('status', 'Status Conference'),
    ('other', 'Other'),
]

HEARING_STATUS_CHOICES = [
    ('scheduled', 'Scheduled'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
    ('postponed', 'Postponed'),
]
```

**Indexes:**

- `hearings_case_id_idx` (on case_id)
- `hearings_hearing_date_idx` (on hearing_date)
- `hearings_status_idx` (on status)

---

### 3. Document (`documents`)

**Purpose:** Legal documents uploaded and processed for AI search.

| Column              | Type         | Constraints                         | Default   | Description             |
| ------------------- | ------------ | ----------------------------------- | --------- | ----------------------- |
| `id`                | SERIAL       | PRIMARY KEY                         | auto      | Unique identifier       |
| `case_id`           | INTEGER      | FK → cases(id) ON DELETE CASCADE    | NULL      | Associated case         |
| `folder_id`         | INTEGER      | FK → folders(id) ON DELETE SET NULL | NULL      | Folder organization     |
| `filename`          | VARCHAR(255) | NOT NULL                            | -         | Original filename       |
| `file_path`         | VARCHAR(500) | NOT NULL                            | -         | Storage path            |
| `file_type`         | VARCHAR(10)  | NULL                                | -         | File extension          |
| `file_size`         | BIGINT       | NULL                                | -         | Size in bytes           |
| `document_type`     | VARCHAR(50)  | NOT NULL                            | -         | Document classification |
| `document_date`     | DATE         | NULL                                | -         | Document date           |
| `processing_status` | VARCHAR(20)  | NOT NULL                            | 'pending' | Processing state        |
| `extracted_text`    | TEXT         | NULL                                | -         | Full extracted text     |
| `chunk_count`       | INTEGER      | NULL                                | -         | Number of chunks        |
| `created_at`        | TIMESTAMP    | NOT NULL                            | NOW()     | Upload timestamp        |

**Choices:**

```python
DOCUMENT_TYPE_CHOICES = [
    ('contract', 'Contract'),
    ('pleading', 'Pleading'),
    ('evidence', 'Evidence'),
    ('correspondence', 'Correspondence'),
    ('brief', 'Brief'),
    ('motion', 'Motion'),
    ('order', 'Order'),
    ('other', 'Other'),
]

PROCESSING_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('processing', 'Processing'),
    ('completed', 'Completed'),
    ('failed', 'Failed'),
]
```

**Indexes:**

- `documents_case_id_idx` (on case_id)
- `documents_processing_status_idx` (on processing_status)
- `documents_document_type_idx` (on document_type)

---

### 4. DocumentChunk (`document_chunks`)

**Purpose:** Chunked text with vector embeddings for semantic search using pgvector.

| Column        | Type        | Constraints                          | Default | Description               |
| ------------- | ----------- | ------------------------------------ | ------- | ------------------------- |
| `id`          | SERIAL      | PRIMARY KEY                          | auto    | Unique identifier         |
| `document_id` | INTEGER     | FK → documents(id) ON DELETE CASCADE | -       | Parent document           |
| `chunk_index` | INTEGER     | NOT NULL                             | -       | Sequence number (0-based) |
| `chunk_text`  | TEXT        | NOT NULL                             | -       | Chunk text content        |
| `embedding`   | VECTOR(768) | NULL                                 | -       | pgvector embedding        |
| `created_at`  | TIMESTAMP   | NOT NULL                             | NOW()   | Creation timestamp        |

**Vector Configuration:**

- Dimensions: **768** (for Ollama nomic-embed-text)
- Alternative: **1536** (for OpenAI text-embedding-3-small)
- Configured via `settings.EMBEDDING_DIMENSIONS`

**Indexes:**

- `document_chunks_document_id_idx` (on document_id)
- `document_chunks_embedding_idx` (ivfflat for vector similarity search)

**SQL for vector index:**

```sql
CREATE INDEX document_chunks_embedding_idx
ON document_chunks
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

---

### 5. Conversation (`conversations`)

**Purpose:** Chat conversation threads for AI Q&A.

| Column            | Type         | Constraints                      | Default | Description        |
| ----------------- | ------------ | -------------------------------- | ------- | ------------------ |
| `id`              | SERIAL       | PRIMARY KEY                      | auto    | Unique identifier  |
| `case_id`         | INTEGER      | FK → cases(id) ON DELETE CASCADE | NULL    | Related case       |
| `title`           | VARCHAR(500) | NULL                             | -       | Conversation title |
| `started_at`      | TIMESTAMP    | NOT NULL                         | NOW()   | Start timestamp    |
| `last_message_at` | TIMESTAMP    | NULL                             | -       | Last activity      |

**Indexes:**

- `conversations_case_id_idx` (on case_id)

---

### 6. Message (`messages`)

**Purpose:** Individual messages in a conversation.

| Column            | Type        | Constraints                              | Default | Description         |
| ----------------- | ----------- | ---------------------------------------- | ------- | ------------------- |
| `id`              | SERIAL      | PRIMARY KEY                              | auto    | Unique identifier   |
| `conversation_id` | INTEGER     | FK → conversations(id) ON DELETE CASCADE | -       | Parent conversation |
| `role`            | VARCHAR(20) | NOT NULL                                 | -       | Message role        |
| `content`         | TEXT        | NOT NULL                                 | -       | Message text        |
| `created_at`      | TIMESTAMP   | NOT NULL                                 | NOW()   | Timestamp           |

**Choices:**

```python
ROLE_CHOICES = [
    ('user', 'User'),
    ('assistant', 'Assistant'),
    ('system', 'System'),
]
```

**Indexes:**

- `messages_conversation_id_idx` (on conversation_id)

---

### 7. Citation (`citations`)

**Purpose:** Source citations for AI-generated answers.

| Column          | Type        | Constraints                                 | Default | Description         |
| --------------- | ----------- | ------------------------------------------- | ------- | ------------------- |
| `id`            | SERIAL      | PRIMARY KEY                                 | auto    | Unique identifier   |
| `message_id`    | INTEGER     | FK → messages(id) ON DELETE CASCADE         | -       | Parent message      |
| `source_type`   | VARCHAR(20) | NOT NULL                                    | -       | Source type         |
| `document_id`   | INTEGER     | FK → documents(id) ON DELETE SET NULL       | NULL    | Referenced document |
| `email_id`      | INTEGER     | FK → emails(id) ON DELETE SET NULL          | NULL    | Referenced email    |
| `chunk_id`      | INTEGER     | FK → document_chunks(id) ON DELETE SET NULL | NULL    | Referenced chunk    |
| `citation_text` | TEXT        | NULL                                        | -       | Quoted text         |
| `created_at`    | TIMESTAMP   | NOT NULL                                    | NOW()   | Timestamp           |

**Choices:**

```python
SOURCE_TYPE_CHOICES = [
    ('document', 'Document'),
    ('email', 'Email'),
    ('chunk', 'Chunk'),
]
```

---

### 8. Email (`emails`)

**Purpose:** Synced Gmail messages.

| Column             | Type         | Constraints                      | Default | Description           |
| ------------------ | ------------ | -------------------------------- | ------- | --------------------- |
| `id`               | SERIAL       | PRIMARY KEY                      | auto    | Unique identifier     |
| `gmail_message_id` | VARCHAR(100) | UNIQUE, NOT NULL                 | -       | Gmail message ID      |
| `gmail_thread_id`  | VARCHAR(100) | NULL                             | -       | Gmail thread ID       |
| `case_id`          | INTEGER      | FK → cases(id) ON DELETE CASCADE | NULL    | Linked case           |
| `subject`          | TEXT         | NULL                             | -       | Email subject         |
| `sender`           | VARCHAR(255) | NULL                             | -       | Sender address        |
| `recipients`       | TEXT         | NULL                             | -       | Recipient list (JSON) |
| `sent_at`          | TIMESTAMP    | NULL                             | -       | Send timestamp        |
| `body_text`        | TEXT         | NULL                             | -       | Email body            |
| `has_attachments`  | BOOLEAN      | NOT NULL                         | FALSE   | Has attachments flag  |
| `created_at`       | TIMESTAMP    | NOT NULL                         | NOW()   | Sync timestamp        |

**Indexes:**

- `emails_gmail_message_id_key` (UNIQUE)
- `emails_case_id_idx` (on case_id)
- `emails_sent_at_idx` (on sent_at)

---

### 9. EmailAttachment (`email_attachments`)

**Purpose:** Attachments from synced emails.

| Column                | Type         | Constraints                           | Default | Description         |
| --------------------- | ------------ | ------------------------------------- | ------- | ------------------- |
| `id`                  | SERIAL       | PRIMARY KEY                           | auto    | Unique identifier   |
| `email_id`            | INTEGER      | FK → emails(id) ON DELETE CASCADE     | -       | Parent email        |
| `filename`            | VARCHAR(255) | NOT NULL                              | -       | Attachment filename |
| `file_path`           | VARCHAR(500) | NULL                                  | -       | Storage path        |
| `gmail_attachment_id` | VARCHAR(100) | NULL                                  | -       | Gmail attachment ID |
| `document_id`         | INTEGER      | FK → documents(id) ON DELETE SET NULL | NULL    | Linked document     |
| `created_at`          | TIMESTAMP    | NOT NULL                              | NOW()   | Timestamp           |

---

### 10. GmailCredential (`gmail_credentials`)

**Purpose:** OAuth tokens for Gmail integration.

| Column          | Type         | Constraints      | Default | Description         |
| --------------- | ------------ | ---------------- | ------- | ------------------- |
| `id`            | SERIAL       | PRIMARY KEY      | auto    | Unique identifier   |
| `email_address` | VARCHAR(254) | UNIQUE, NOT NULL | -       | Gmail address       |
| `access_token`  | TEXT         | NOT NULL         | -       | OAuth access token  |
| `refresh_token` | TEXT         | NOT NULL         | -       | OAuth refresh token |
| `token_expiry`  | TIMESTAMP    | NOT NULL         | -       | Token expiration    |
| `scope`         | TEXT         | NOT NULL         | default | Gmail API scope     |
| `is_active`     | BOOLEAN      | NOT NULL         | TRUE    | Active flag         |
| `created_at`    | TIMESTAMP    | NOT NULL         | NOW()   | Creation timestamp  |
| `updated_at`    | TIMESTAMP    | NOT NULL         | NOW()   | Update timestamp    |

---

### 11. Task (`tasks`)

**Purpose:** Task management for cases.

| Column        | Type         | Constraints                      | Default   | Description        |
| ------------- | ------------ | -------------------------------- | --------- | ------------------ |
| `id`          | SERIAL       | PRIMARY KEY                      | auto      | Unique identifier  |
| `case_id`     | INTEGER      | FK → cases(id) ON DELETE CASCADE | NULL      | Related case       |
| `title`       | VARCHAR(255) | NULL                             | -         | Task title         |
| `description` | TEXT         | NULL                             | -         | Task details       |
| `status`      | VARCHAR(20)  | NOT NULL                         | 'pending' | Task status        |
| `due_date`    | TIMESTAMP    | NULL                             | -         | Due date           |
| `created_at`  | TIMESTAMP    | NOT NULL                         | NOW()     | Creation timestamp |

**Choices:**

```python
TASK_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('in_progress', 'In Progress'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
]
```

---

### 12. ActivityLog (`activity_logs`)

**Purpose:** Audit trail for case activities.

| Column          | Type        | Constraints                      | Default | Description          |
| --------------- | ----------- | -------------------------------- | ------- | -------------------- |
| `id`            | SERIAL      | PRIMARY KEY                      | auto    | Unique identifier    |
| `case_id`       | INTEGER     | FK → cases(id) ON DELETE CASCADE | NULL    | Related case         |
| `activity_type` | VARCHAR(50) | NULL                             | -       | Activity type        |
| `description`   | TEXT        | NULL                             | -       | Activity description |
| `created_at`    | TIMESTAMP   | NOT NULL                         | NOW()   | Timestamp            |

---

### 13. Folder (`folders`)

**Purpose:** Document folder organization (supports nesting).

| Column             | Type         | Constraints                        | Default | Description        |
| ------------------ | ------------ | ---------------------------------- | ------- | ------------------ |
| `id`               | SERIAL       | PRIMARY KEY                        | auto    | Unique identifier  |
| `name`             | VARCHAR(255) | NOT NULL                           | -       | Folder name        |
| `parent_folder_id` | INTEGER      | FK → folders(id) ON DELETE CASCADE | NULL    | Parent folder      |
| `created_at`       | TIMESTAMP    | NOT NULL                           | NOW()   | Creation timestamp |

---

### 14. CaseTag (`case_tags`)

**Purpose:** Tag definitions for cases.

| Column | Type         | Constraints      | Default | Description       |
| ------ | ------------ | ---------------- | ------- | ----------------- |
| `id`   | SERIAL       | PRIMARY KEY      | auto    | Unique identifier |
| `name` | VARCHAR(100) | UNIQUE, NOT NULL | -       | Tag name          |

---

### 15. CaseTagMap (`case_tag_map`)

**Purpose:** Many-to-many mapping between cases and tags.

| Column    | Type    | Constraints                          | Default | Description       |
| --------- | ------- | ------------------------------------ | ------- | ----------------- |
| `id`      | SERIAL  | PRIMARY KEY                          | auto    | Unique identifier |
| `case_id` | INTEGER | FK → cases(id) ON DELETE CASCADE     | -       | Case reference    |
| `tag_id`  | INTEGER | FK → case_tags(id) ON DELETE CASCADE | -       | Tag reference     |

**Constraints:**

- `UNIQUE (case_id, tag_id)` - Prevents duplicate mappings

---

### 16. DocumentTag (`document_tags`)

**Purpose:** Tag definitions for documents.

| Column | Type         | Constraints      | Default | Description       |
| ------ | ------------ | ---------------- | ------- | ----------------- |
| `id`   | SERIAL       | PRIMARY KEY      | auto    | Unique identifier |
| `name` | VARCHAR(100) | UNIQUE, NOT NULL | -       | Tag name          |

---

### 17. DocumentTagMap (`document_tag_map`)

**Purpose:** Many-to-many mapping between documents and tags.

| Column        | Type    | Constraints                              | Default | Description        |
| ------------- | ------- | ---------------------------------------- | ------- | ------------------ |
| `id`          | SERIAL  | PRIMARY KEY                              | auto    | Unique identifier  |
| `document_id` | INTEGER | FK → documents(id) ON DELETE CASCADE     | -       | Document reference |
| `tag_id`      | INTEGER | FK → document_tags(id) ON DELETE CASCADE | -       | Tag reference      |

**Constraints:**

- `UNIQUE (document_id, tag_id)` - Prevents duplicate mappings

---

### 18. DocumentVersion (`document_versions`)

**Purpose:** Version history for documents.

| Column           | Type         | Constraints                          | Default | Description        |
| ---------------- | ------------ | ------------------------------------ | ------- | ------------------ |
| `id`             | SERIAL       | PRIMARY KEY                          | auto    | Unique identifier  |
| `document_id`    | INTEGER      | FK → documents(id) ON DELETE CASCADE | -       | Parent document    |
| `version_number` | INTEGER      | NOT NULL                             | -       | Version number     |
| `file_path`      | VARCHAR(500) | NULL                                 | -       | Storage path       |
| `created_at`     | TIMESTAMP    | NOT NULL                             | NOW()   | Creation timestamp |

---

## pgvector Configuration

### Extension Setup

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Embedding Dimensions

| AI Provider | Model                  | Dimensions |
| ----------- | ---------------------- | ---------- |
| Ollama      | nomic-embed-text       | 768        |
| OpenAI      | text-embedding-3-small | 1536       |

### Vector Similarity Search

```sql
-- Find similar chunks using cosine similarity
SELECT
    dc.id,
    dc.chunk_text,
    1 - (dc.embedding <=> query_embedding) AS similarity
FROM document_chunks dc
WHERE dc.embedding IS NOT NULL
ORDER BY dc.embedding <=> query_embedding
LIMIT 10;
```

---

## Migrations

| Migration                            | Description                                   |
| ------------------------------------ | --------------------------------------------- |
| `0001_initial`                       | Create all tables                             |
| `0002_alter_documentchunk_embedding` | Change VectorField from 1536 → 768 dimensions |

---

## Performance Considerations

1. **Indexes**: All foreign keys and frequently-filtered columns are indexed
2. **Vector Index**: IVFFlat index on embeddings for fast similarity search
3. **Cascade Deletes**: Proper CASCADE rules prevent orphaned records
4. **Text Fields**: Large text content (extracted_text, body_text) stored as TEXT type
5. **Timestamps**: All tables have created_at for audit purposes
