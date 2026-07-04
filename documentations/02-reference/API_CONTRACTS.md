# API Contracts

Base URL in local development: `http://localhost:8000/api`

The contracts below reflect the current checked-in URLconf and serializers/views.

## General

- Authentication: none in the current API layer
- Format: JSON except `POST /api/documents/upload/`, which uses `multipart/form-data`
- Root routing: `case_intel_project/urls.py` mounts `path("api/", include("core.urls"))`

## Dashboard

### `GET /dashboard/`

Returns:

```json
{
  "stats": {
    "active_cases": 4,
    "total_documents": 10,
    "email_threads": 49,
    "documents_by_status": {"completed": 10},
    "cases_by_priority": {"medium": 3, "critical": 1},
    "cases_by_status": {"open": 4}
  },
  "recent_emails": [
    {
      "id": 1,
      "subject": "Example",
      "sender": "sender@example.com",
      "sent_at": "2026-04-02T18:48:55Z",
      "case_id": 1,
      "case_title": "test case"
    }
  ],
  "recent_activity": [
    {
      "id": 1,
      "activity_type": "document_uploaded",
      "description": "Uploaded motion.pdf",
      "created_at": "2026-07-04T09:00:00Z",
      "case_id": 4
    }
  ],
  "active_cases_summary": [
    {
      "id": 4,
      "case_number": "4",
      "title": "claude testcase",
      "document_count": 3,
      "priority": "medium",
      "status": "open"
    }
  ]
}
```

## Chat

### `POST /chat/`

Request:

```json
{
  "query": "What were the key arguments?",
  "case_id": 4,
  "conversation_id": 12
}
```

`case_id` and `conversation_id` are optional.

Response:

```json
{
  "answer": "Assistant response text",
  "confidence": 0.82,
  "query_type": "simple_qa",
  "requires_clarification": false,
  "clarification_question": null,
  "message_id": 51,
  "conversation_id": 12,
  "citations": [
    {
      "chunk_id": 7,
      "document_id": 3,
      "citation_text": "Supporting quote",
      "source_type": "chunk"
    }
  ]
}
```

Behavior notes:

- if `conversation_id` is omitted, the backend creates a new `Conversation`
- conversation titles are currently seeded from the opening query text in `AIWorkflowService._get_or_create_conversation()`
- the answer text may already include a markdown `**Sources:**` block because `response_formatter()` appends one

## Conversations

### `GET /conversations/`

Optional query params:

- `case_id`

Response shape:

```json
[
  {
    "id": 12,
    "case_id": 4,
    "title": "Summarize the motion to dismiss",
    "started_at": "2026-07-04T09:15:00Z",
    "last_message_at": "2026-07-04T09:16:10Z",
    "message_count": 4
  }
]
```

### `GET /conversations/{id}/`

Response shape:

```json
{
  "id": 12,
  "case_id": 4,
  "title": "Summarize the motion to dismiss",
  "started_at": "2026-07-04T09:15:00Z",
  "last_message_at": "2026-07-04T09:16:10Z",
  "messages": [
    {
      "id": 50,
      "role": "user",
      "content": "Summarize the motion",
      "created_at": "2026-07-04T09:15:03Z",
      "citations": []
    },
    {
      "id": 51,
      "role": "assistant",
      "content": "Here is the summary...",
      "created_at": "2026-07-04T09:15:10Z",
      "citations": [
        {
          "id": 3,
          "source_type": "chunk",
          "document_id": 3,
          "chunk_id": 7,
          "citation_text": "Supporting quote",
          "created_at": "2026-07-04T09:15:10Z"
        }
      ]
    }
  ]
}
```

### `DELETE /conversations/{id}/`

Returns `204 No Content`.

### Not Present In Current URLconf

- no `GET /conversations/{id}/messages/`
- no `GET /conversations/{id}/export/`

## Cases

### `GET /cases/`

Optional query params:

- `status`
- `priority`
- `case_type`

Response objects contain:

```json
{
  "id": 4,
  "case_number": "4",
  "title": "claude testcase",
  "client_name": "Client",
  "opposing_party": null,
  "case_type": "civil",
  "status": "open",
  "priority": "medium",
  "filing_date": null,
  "notes": null,
  "created_at": "2026-07-01T10:00:00Z",
  "document_count": 3,
  "hearing_count": 0,
  "thread_count": 1,
  "conversation_count": 2
}
```

### `POST /cases/`

Writable fields:

- `case_number`
- `title`
- `client_name`
- `opposing_party`
- `case_type`
- `status`
- `priority`
- `filing_date`
- `notes`

### `GET /cases/{id}/`
### `PATCH /cases/{id}/`
### `DELETE /cases/{id}/`

`GET` and `PATCH` use the same shape as list items.

## Hearings

### `GET /hearings/`

Optional query params:

- `case_id`
- `status`
- `upcoming=true`
- `past=true`

Response shape:

```json
[
  {
    "id": 1,
    "case": 4,
    "case_title": "claude testcase",
    "hearing_date": "2026-07-20T10:30:00Z",
    "hearing_type": "motion",
    "hearing_type_display": "Motion Hearing",
    "location": "Courtroom 2",
    "judge": "Justice Rao",
    "status": "scheduled",
    "status_display": "Scheduled",
    "notes": null,
    "outcome": null,
    "created_at": "2026-07-01T10:00:00Z",
    "updated_at": "2026-07-01T10:00:00Z"
  }
]
```

### `POST /hearings/`
### `GET /hearings/{id}/`
### `PATCH /hearings/{id}/`
### `DELETE /hearings/{id}/`

The serializer writes:

- `case`
- `hearing_date`
- `hearing_type`
- `location`
- `judge`
- `status`
- `notes`
- `outcome`

## Documents

### `GET /documents/`

Optional query params:

- `case_id`

Response shape:

```json
{
  "id": 9,
  "case_id": 4,
  "case": {
    "id": 4,
    "title": "claude testcase",
    "case_number": "4",
    "client_name": "Client"
  },
  "case_title": "claude testcase",
  "folder": null,
  "folder_name": null,
  "filename": "motion.pdf",
  "file_path": "C:\\\\...\\\\media\\\\documents\\\\motion.pdf",
  "file_type": "pdf",
  "file_size": 12345,
  "document_type": "motion",
  "document_date": null,
  "processing_status": "completed",
  "chunk_count": 8,
  "created_at": "2026-07-04T08:00:00Z"
}
```

### `POST /documents/upload/`

Multipart fields:

- `file` required
- `case_id` optional
- `folder_id` optional in serializer, though the current view only uses `case_id`
- `document_type` optional

Allowed extensions:

- `pdf`
- `txt`
- `docx`
- `doc`

Max upload size: `50 MB`

### `GET /documents/{id}/`
### `PATCH /documents/{id}/`
### `DELETE /documents/{id}/`

### `POST /documents/{id}/process/`

Triggers synchronous extraction, chunking, and embedding generation, then returns the updated document object.

## Folders

### `GET /folders/`

Returns the `FolderSerializer` list ordered by name.

## Gmail

### `GET /gmail/auth/`

Returns:

```json
{"auth_url": "https://accounts.google.com/o/oauth2/v2/auth?..."}
```

### `GET /gmail/callback/?code=...`

This is a GET endpoint, not POST.

Success response:

```json
{
  "message": "Gmail connected successfully",
  "email": "user@example.com"
}
```

### `GET /gmail/status/`

Response when disconnected:

```json
{"connected": false}
```

Response when connected:

```json
{
  "connected": true,
  "email": "bhagathsamalla0@gmail.com",
  "last_sync": null
}
```

### `POST /gmail/sync/`

Accepted request keys:

- `labels`
- `max_results`
- `days_back`

Response:

```json
{
  "synced_count": 5,
  "emails": [
    {"id": 41, "subject": "Example subject"}
  ]
}
```

### Not Present In Current URLconf

- no `POST /gmail/disconnect/`

## Emails

### `GET /emails/`

Optional query params:

- `case_id`
- `unlinked=true`

Response shape:

```json
[
  {
    "id": 1,
    "subject": "2-Step Verification turned on",
    "sender": "Google <no-reply@accounts.google.com>",
    "sent_at": "2026-04-02T18:48:55Z",
    "has_attachments": false,
    "case_id": 1,
    "case_title": "test case"
  }
]
```

### `POST /emails/{id}/link/`

Request:

```json
{"case_id": 4}
```

Response:

```json
{
  "message": "Email linked to case",
  "case_id": 4
}
```

## Known Frontend/API Mismatches

These are important for anyone debugging the current UI:

- the frontend Gmail callback helper posts JSON to `/gmail/callback/`, but the backend expects `GET` with a `code` query param
- the frontend defines a `/gmail/disconnect/` call, but the backend does not expose that route
- the email table component expects richer fields such as `linked_case`, `sender_email`, and `received_date`, while `GET /emails/` returns the simpler shape documented above
- the Gmail status card prefers `is_connected`, `email_address`, and `last_sync_time`, while the backend returns `connected`, `email`, and `last_sync`
