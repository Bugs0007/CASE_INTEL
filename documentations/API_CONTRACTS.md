# Case Intel - API Contracts Documentation

**Last Updated:** March 2026
**Base URL:** `http://localhost:8000/api`
**Content-Type:** `application/json` (unless specified otherwise)

---

## Overview

| Category      | Endpoints | Description             |
| ------------- | --------- | ----------------------- |
| Dashboard     | 1         | Aggregated statistics   |
| Chat          | 1         | AI Q&A processing       |
| Cases         | 5         | Case CRUD operations    |
| Hearings      | 5         | Hearing CRUD operations |
| Documents     | 5         | Document management     |
| Conversations | 3         | Chat history            |
| Gmail         | 4         | Gmail OAuth & sync      |
| Emails        | 2         | Email management        |

---

## Authentication

Currently, no authentication is required. Future versions will implement JWT authentication.

---

## Common Response Codes

| Code | Description                         |
| ---- | ----------------------------------- |
| 200  | Success                             |
| 201  | Created                             |
| 204  | No Content (successful delete)      |
| 400  | Bad Request (validation error)      |
| 404  | Not Found                           |
| 409  | Conflict (e.g., already processing) |
| 500  | Internal Server Error               |

---

## Dashboard

### GET /api/dashboard/

Get aggregated dashboard statistics including counts, recent activity, and case summaries.

**Request:**

```
GET /api/dashboard/
```

**Response (200):**

```json
{
  "stats": {
    "active_cases": 5,
    "total_documents": 42,
    "email_threads": 12,
    "documents_by_status": {
      "pending": 2,
      "processing": 1,
      "completed": 39,
      "failed": 0
    },
    "cases_by_priority": {
      "low": 1,
      "medium": 2,
      "high": 1,
      "critical": 1
    },
    "cases_by_status": {
      "open": 5,
      "closed": 10,
      "pending": 3,
      "archived": 2
    }
  },
  "recent_emails": [
    {
      "id": 1,
      "subject": "Re: Discovery Documents",
      "sender": "attorney@lawfirm.com",
      "sent_at": "2024-03-20T14:30:00Z",
      "case_id": 1,
      "case_title": "Smith v. Jones"
    }
  ],
  "recent_activity": [
    {
      "id": 1,
      "activity_type": "document_uploaded",
      "description": "Uploaded motion_to_dismiss.pdf",
      "created_at": "2024-03-20T10:00:00Z",
      "case_id": 1
    }
  ],
  "active_cases_summary": [
    {
      "id": 1,
      "case_number": "2024-CV-001",
      "title": "Smith v. Jones",
      "document_count": 15,
      "priority": "high",
      "status": "open"
    }
  ]
}
```

---

## Chat (AI Q&A)

### POST /api/chat/

Process a user question through the LangGraph AI pipeline. The system performs semantic search across case documents and generates an answer with citations.

**Request:**

```json
{
  "query": "What were the key arguments in the motion to dismiss?",
  "case_id": 1,
  "conversation_id": 5
}
```

| Field           | Type    | Required | Description                    |
| --------------- | ------- | -------- | ------------------------------ |
| query           | string  | Yes      | User's question                |
| case_id         | integer | No       | Filter search to specific case |
| conversation_id | integer | No       | Continue existing conversation |

**Response (200):**

```json
{
  "answer": "The motion to dismiss presented three key arguments:\n\n1. **Lack of jurisdiction** - The defendant argued that the court lacks subject matter jurisdiction because...\n\n2. **Failure to state a claim** - The plaintiff's complaint fails to allege sufficient facts to support...\n\n3. **Statute of limitations** - The claims are barred by the applicable two-year statute of limitations...",
  "confidence": 0.87,
  "query_type": "factual",
  "requires_clarification": false,
  "clarification_question": null,
  "message_id": 123,
  "conversation_id": 5,
  "citations": [
    {
      "source_type": "document",
      "document_id": 10,
      "document_name": "motion_to_dismiss.pdf",
      "chunk_id": 45,
      "citation_text": "The defendant moves to dismiss pursuant to Rule 12(b)(6) for failure to state a claim upon which relief can be granted.",
      "relevance_score": 0.92
    },
    {
      "source_type": "document",
      "document_id": 10,
      "document_name": "motion_to_dismiss.pdf",
      "chunk_id": 47,
      "citation_text": "The statute of limitations for this type of claim is two years from the date of discovery.",
      "relevance_score": 0.88
    }
  ]
}
```

| Field                  | Type    | Description                                      |
| ---------------------- | ------- | ------------------------------------------------ |
| answer                 | string  | AI-generated answer                              |
| confidence             | float   | Confidence score (0-1)                           |
| query_type             | string  | Query classification (factual, analytical, etc.) |
| requires_clarification | boolean | Whether clarification is needed                  |
| clarification_question | string  | Follow-up question if clarification needed       |
| message_id             | integer | ID of saved message                              |
| conversation_id        | integer | Conversation ID (new or existing)                |
| citations              | array   | Source citations                                 |

**Error Response (400):**

```json
{
  "error": "Query is required"
}
```

---

## Cases

### GET /api/cases/

List all cases with optional filtering.

**Query Parameters:**

| Parameter | Type   | Description                                        |
| --------- | ------ | -------------------------------------------------- |
| status    | string | Filter by status (open, closed, pending, archived) |
| priority  | string | Filter by priority (low, medium, high, critical)   |
| case_type | string | Filter by type (civil, criminal, family, etc.)     |

**Request:**

```
GET /api/cases/?status=open&priority=high
```

**Response (200):**

```json
[
  {
    "id": 1,
    "case_number": "2024-CV-001",
    "title": "Smith v. Jones",
    "client_name": "John Smith",
    "opposing_party": "Jane Jones",
    "case_type": "civil",
    "status": "open",
    "priority": "high",
    "filing_date": "2024-01-15",
    "notes": "Important contract dispute case",
    "created_at": "2024-01-15T10:00:00Z",
    "document_count": 15,
    "hearing_count": 3,
    "thread_count": 5,
    "conversation_count": 2
  }
]
```

---

### POST /api/cases/

Create a new case.

**Request:**

```json
{
  "case_number": "2024-CV-002",
  "title": "New Case Title",
  "client_name": "Client Name",
  "opposing_party": "Opposing Party",
  "case_type": "civil",
  "status": "open",
  "priority": "medium",
  "filing_date": "2024-03-01",
  "notes": "Additional notes about the case"
}
```

| Field          | Type   | Required | Description                                                     |
| -------------- | ------ | -------- | --------------------------------------------------------------- |
| case_number    | string | Yes      | Unique case identifier                                          |
| title          | string | Yes      | Case title                                                      |
| client_name    | string | Yes      | Client's name                                                   |
| opposing_party | string | No       | Opposing party name                                             |
| case_type      | string | Yes      | Type: civil, criminal, family, corporate, ip, labor, tax, other |
| status         | string | No       | Status: open (default), closed, pending, archived               |
| priority       | string | No       | Priority: low, medium (default), high, critical                 |
| filing_date    | date   | No       | Filing date (YYYY-MM-DD)                                        |
| notes          | string | No       | Additional notes                                                |

**Response (201):**

```json
{
  "id": 2,
  "case_number": "2024-CV-002",
  "title": "New Case Title",
  "client_name": "Client Name",
  "opposing_party": "Opposing Party",
  "case_type": "civil",
  "status": "open",
  "priority": "medium",
  "filing_date": "2024-03-01",
  "notes": "Additional notes about the case",
  "created_at": "2024-03-01T10:00:00Z",
  "document_count": 0,
  "hearing_count": 0,
  "thread_count": 0,
  "conversation_count": 0
}
```

---

### GET /api/cases/{id}/

Retrieve a single case by ID.

**Request:**

```
GET /api/cases/1/
```

**Response (200):**

```json
{
  "id": 1,
  "case_number": "2024-CV-001",
  "title": "Smith v. Jones",
  "client_name": "John Smith",
  "opposing_party": "Jane Jones",
  "case_type": "civil",
  "status": "open",
  "priority": "high",
  "filing_date": "2024-01-15",
  "notes": "Important contract dispute case",
  "created_at": "2024-01-15T10:00:00Z",
  "document_count": 15,
  "hearing_count": 3,
  "thread_count": 5,
  "conversation_count": 2
}
```

**Response (404):**

```json
{
  "detail": "Not found."
}
```

---

### PATCH /api/cases/{id}/

Update a case (partial update).

**Request:**

```json
{
  "status": "closed",
  "notes": "Case resolved through settlement"
}
```

**Response (200):**

```json
{
  "id": 1,
  "case_number": "2024-CV-001",
  "title": "Smith v. Jones",
  "client_name": "John Smith",
  "opposing_party": "Jane Jones",
  "case_type": "civil",
  "status": "closed",
  "priority": "high",
  "filing_date": "2024-01-15",
  "notes": "Case resolved through settlement",
  "created_at": "2024-01-15T10:00:00Z",
  "document_count": 15,
  "hearing_count": 3,
  "thread_count": 5,
  "conversation_count": 2
}
```

---

### DELETE /api/cases/{id}/

Delete a case and all related data (cascades).

**Request:**

```
DELETE /api/cases/1/
```

**Response (204):** No content

---

## Hearings

### GET /api/hearings/

List hearings with optional filtering.

**Query Parameters:**

| Parameter | Type    | Description                    |
| --------- | ------- | ------------------------------ |
| case_id   | integer | Filter by case                 |
| status    | string  | Filter by status               |
| upcoming  | boolean | Set `true` for future hearings |
| past      | boolean | Set `true` for past hearings   |

**Request:**

```
GET /api/hearings/?case_id=1&upcoming=true
```

**Response (200):**

```json
[
  {
    "id": 1,
    "case": 1,
    "case_title": "Smith v. Jones",
    "hearing_date": "2024-04-15T09:00:00Z",
    "hearing_type": "motion",
    "hearing_type_display": "Motion Hearing",
    "location": "Courtroom 5A, County Courthouse",
    "judge": "Hon. William Roberts",
    "status": "scheduled",
    "status_display": "Scheduled",
    "notes": "Motion to dismiss hearing",
    "outcome": null,
    "created_at": "2024-03-01T10:00:00Z",
    "updated_at": "2024-03-01T10:00:00Z"
  }
]
```

---

### POST /api/hearings/

Create a new hearing.

**Request:**

```json
{
  "case": 1,
  "hearing_date": "2024-04-15T09:00:00Z",
  "hearing_type": "motion",
  "location": "Courtroom 5A, County Courthouse",
  "judge": "Hon. William Roberts",
  "status": "scheduled",
  "notes": "Motion to dismiss hearing"
}
```

| Field        | Type     | Required | Description                                                                |
| ------------ | -------- | -------- | -------------------------------------------------------------------------- |
| case         | integer  | Yes      | Case ID                                                                    |
| hearing_date | datetime | Yes      | ISO 8601 format                                                            |
| hearing_type | string   | Yes      | preliminary, motion, trial, appeal, sentencing, arraignment, status, other |
| location     | string   | No       | Court location                                                             |
| judge        | string   | No       | Judge name                                                                 |
| status       | string   | No       | scheduled (default), completed, cancelled, postponed                       |
| notes        | string   | No       | Pre-hearing notes                                                          |

**Response (201):**

```json
{
  "id": 1,
  "case": 1,
  "case_title": "Smith v. Jones",
  "hearing_date": "2024-04-15T09:00:00Z",
  "hearing_type": "motion",
  "hearing_type_display": "Motion Hearing",
  "location": "Courtroom 5A, County Courthouse",
  "judge": "Hon. William Roberts",
  "status": "scheduled",
  "status_display": "Scheduled",
  "notes": "Motion to dismiss hearing",
  "outcome": null,
  "created_at": "2024-03-01T10:00:00Z",
  "updated_at": "2024-03-01T10:00:00Z"
}
```

---

### GET /api/hearings/{id}/

Retrieve a single hearing.

**Response (200):** Same format as list item

---

### PATCH /api/hearings/{id}/

Update a hearing.

**Request:**

```json
{
  "status": "completed",
  "outcome": "Motion denied. Case proceeds to trial."
}
```

**Response (200):** Updated hearing object

---

### DELETE /api/hearings/{id}/

Delete a hearing.

**Response (204):** No content

---

## Documents

### GET /api/documents/

List documents with optional case filtering.

**Query Parameters:**

| Parameter | Type    | Description    |
| --------- | ------- | -------------- |
| case_id   | integer | Filter by case |

**Request:**

```
GET /api/documents/?case_id=1
```

**Response (200):**

```json
[
  {
    "id": 1,
    "case_id": 1,
    "case_title": "Smith v. Jones",
    "filename": "motion_to_dismiss.pdf",
    "file_path": "/media/documents/motion_to_dismiss.pdf",
    "file_type": "pdf",
    "file_size": 1048576,
    "document_type": "motion",
    "document_date": "2024-01-20",
    "processing_status": "completed",
    "chunk_count": 15,
    "created_at": "2024-01-20T10:00:00Z"
  }
]
```

---

### GET /api/documents/{id}/

Retrieve a single document.

**Response (200):** Same format as list item

---

### DELETE /api/documents/{id}/

Delete a document and all its chunks.

**Response (204):** No content

---

### POST /api/documents/upload/

Upload a document file.

**Content-Type:** `multipart/form-data`

**Form Fields:**

| Field         | Type    | Required | Description                         |
| ------------- | ------- | -------- | ----------------------------------- |
| file          | file    | Yes      | Document file (pdf, txt, docx, doc) |
| case_id       | integer | No       | Case to associate with              |
| document_type | string  | No       | Document classification             |

**cURL Example:**

```bash
curl -X POST http://localhost:8000/api/documents/upload/ \
  -F "file=@motion.pdf" \
  -F "case_id=1" \
  -F "document_type=motion"
```

**Response (201):**

```json
{
  "id": 5,
  "case_id": 1,
  "filename": "motion.pdf",
  "file_path": "/media/documents/abc123_motion.pdf",
  "file_type": "pdf",
  "file_size": 524288,
  "document_type": "motion",
  "document_date": null,
  "processing_status": "pending",
  "chunk_count": null,
  "created_at": "2024-03-20T10:00:00Z"
}
```

**Error Response (400):**

```json
{
  "error": "No file provided"
}
```

```json
{
  "error": "File type '.exe' is not allowed. Allowed types: pdf, txt, docx, doc"
}
```

```json
{
  "error": "File size exceeds 50MB limit"
}
```

---

### POST /api/documents/{id}/process/

Trigger document processing: extract text, chunk, and generate embeddings.

**Request:**

```
POST /api/documents/5/process/
```

**Response (200):**

```json
{
  "id": 5,
  "case_id": 1,
  "filename": "motion.pdf",
  "file_path": "/media/documents/abc123_motion.pdf",
  "file_type": "pdf",
  "file_size": 524288,
  "document_type": "motion",
  "document_date": null,
  "processing_status": "completed",
  "chunk_count": 12,
  "created_at": "2024-03-20T10:00:00Z"
}
```

**Error Responses:**

**404 - Document not found:**

```json
{
  "error": "Document not found"
}
```

**409 - Already processing:**

```json
{
  "error": "Document is already being processed"
}
```

**500 - Processing failed:**

```json
{
  "error": "Processing failed: Unable to extract text from file"
}
```

---

## Conversations

### GET /api/conversations/

List conversations with optional case filtering.

**Query Parameters:**

| Parameter | Type    | Description    |
| --------- | ------- | -------------- |
| case_id   | integer | Filter by case |

**Request:**

```
GET /api/conversations/?case_id=1
```

**Response (200):**

```json
[
  {
    "id": 1,
    "case_id": 1,
    "case_title": "Smith v. Jones",
    "title": "Questions about motion to dismiss",
    "started_at": "2024-03-01T10:00:00Z",
    "last_message_at": "2024-03-01T11:30:00Z",
    "message_count": 6
  }
]
```

---

### GET /api/conversations/{id}/

Retrieve a conversation with all messages and citations.

**Response (200):**

```json
{
  "id": 1,
  "case_id": 1,
  "case_title": "Smith v. Jones",
  "title": "Questions about motion to dismiss",
  "started_at": "2024-03-01T10:00:00Z",
  "last_message_at": "2024-03-01T11:30:00Z",
  "messages": [
    {
      "id": 1,
      "role": "user",
      "content": "What are the key arguments in the motion to dismiss?",
      "created_at": "2024-03-01T10:00:00Z",
      "citations": []
    },
    {
      "id": 2,
      "role": "assistant",
      "content": "The motion to dismiss presents three key arguments...",
      "created_at": "2024-03-01T10:00:05Z",
      "citations": [
        {
          "id": 1,
          "source_type": "document",
          "document_id": 5,
          "chunk_id": 12,
          "citation_text": "The defendant moves to dismiss...",
          "created_at": "2024-03-01T10:00:05Z"
        }
      ]
    }
  ]
}
```

---

### DELETE /api/conversations/{id}/

Delete a conversation and all its messages.

**Response (204):** No content

---

## Gmail Integration

### GET /api/gmail/auth/

Initiate Gmail OAuth flow. Returns a URL for the user to authorize access.

**Response (200):**

```json
{
  "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=...&redirect_uri=...&scope=..."
}
```

---

### GET /api/gmail/callback/?code={code}

Handle OAuth callback after Google authorization.

**Query Parameters:**

| Parameter | Type   | Description                    |
| --------- | ------ | ------------------------------ |
| code      | string | Authorization code from Google |

**Response (200):**

```json
{
  "message": "Gmail connected successfully",
  "email": "user@gmail.com"
}
```

**Error Response (400):**

```json
{
  "error": "Authorization code is required"
}
```

**Error Response (500):**

```json
{
  "error": "Failed to exchange authorization code"
}
```

---

### GET /api/gmail/status/

Check Gmail connection status.

**Response (200) - Connected:**

```json
{
  "connected": true,
  "email": "user@gmail.com",
  "last_sync": "2024-03-20T10:00:00Z"
}
```

**Response (200) - Not connected:**

```json
{
  "connected": false
}
```

---

### POST /api/gmail/sync/

Trigger email synchronization from Gmail.

**Request:**

```json
{
  "labels": ["INBOX"],
  "max_results": 50,
  "days_back": 7
}
```

| Field       | Type    | Default   | Description            |
| ----------- | ------- | --------- | ---------------------- |
| labels      | array   | ["INBOX"] | Gmail labels to sync   |
| max_results | integer | 50        | Maximum emails to sync |
| days_back   | integer | 7         | Days to look back      |

**Response (200):**

```json
{
  "synced_count": 12,
  "emails": [
    {
      "id": 1,
      "subject": "Re: Case Update",
      "sender": "attorney@lawfirm.com",
      "sent_at": "2024-03-20T10:00:00Z"
    }
  ]
}
```

**Error Response (400):**

```json
{
  "error": "Gmail is not connected. Please authorize first."
}
```

---

## Emails

### GET /api/emails/

List synced emails with optional filtering.

**Query Parameters:**

| Parameter | Type    | Description                         |
| --------- | ------- | ----------------------------------- |
| case_id   | integer | Filter by linked case               |
| unlinked  | boolean | Set `true` for unlinked emails only |

**Request:**

```
GET /api/emails/?unlinked=true
```

**Response (200):**

```json
[
  {
    "id": 1,
    "gmail_message_id": "abc123xyz",
    "subject": "Re: Discovery Documents",
    "sender": "attorney@lawfirm.com",
    "recipients": "client@email.com, paralegal@lawfirm.com",
    "sent_at": "2024-03-20T14:30:00Z",
    "has_attachments": true,
    "case_id": null,
    "case_title": null,
    "suggested_case_id": 1,
    "suggested_case_title": "Smith v. Jones"
  }
]
```

---

### POST /api/emails/{id}/link/

Link an email to a case.

**Request:**

```json
{
  "case_id": 1
}
```

**Response (200):**

```json
{
  "message": "Email linked to case",
  "email_id": 1,
  "case_id": 1,
  "case_title": "Smith v. Jones"
}
```

**Error Response (400):**

```json
{
  "error": "Case ID is required"
}
```

**Error Response (404):**

```json
{
  "error": "Case not found"
}
```

---

## Error Handling

All endpoints return errors in a consistent format:

**Validation Error (400):**

```json
{
  "field_name": ["Error message 1", "Error message 2"],
  "other_field": ["Another error"]
}
```

**Not Found (404):**

```json
{
  "detail": "Not found."
}
```

**Server Error (500):**

```json
{
  "error": "Descriptive error message"
}
```

---

## Rate Limiting

Currently not implemented. Future versions may include:

- 100 requests/minute for standard endpoints
- 10 requests/minute for AI chat endpoint

---

## Pagination

Large result sets will include pagination (future implementation):

```json
{
  "count": 100,
  "next": "http://localhost:8000/api/cases/?page=2",
  "previous": null,
  "results": [...]
}
```
