# Database Schema

This schema reference is based on the current models plus the applied migrations reported by `manage.py showmigrations core`.

## Migration State

Applied `core` migrations:

- `0000_vector_extension`
- `0001_initial`
- `0002_alter_activitylog_id_alter_case_id_alter_casetag_id_and_more`
- `0003_gmailcredential_hearing`
- `0004_alter_activitylog_id_alter_case_id_alter_casetag_id_and_more`

## Table Counts

Current database inventory:

- 18 domain tables from the `core` app
- 13 framework tables from Django auth/session/admin and Celery result/beat apps
- 31 tables total in the dev database

## Domain Tables

### Case Management

`cases`
- `id`, `case_number`, `title`, `client_name`
- `opposing_party`, `case_type`, `status`, `priority`
- `filing_date`, `notes`, `created_at`

`hearings`
- `id`, `case_id`
- `hearing_date`, `hearing_type`, `location`, `judge`
- `status`, `notes`, `outcome`
- `created_at`, `updated_at`

`activity_logs`
- `id`, `case_id`
- `activity_type`, `description`, `created_at`

`tasks`
- `id`, `case_id`
- `title`, `description`, `status`, `due_date`, `created_at`

### Documents

`documents`
- `id`, `case_id`, `folder_id`
- `filename`, `file_path`, `file_type`, `file_size`
- `document_type`, `document_date`
- `processing_status`, `extracted_text`, `chunk_count`, `created_at`

`document_versions`
- `id`, `document_id`
- `version_number`, `file_path`, `created_at`

`document_chunks`
- `id`, `document_id`
- `chunk_index`, `chunk_text`
- `embedding` as `VectorField(dimensions=768)`
- `created_at`

`folders`
- `id`, `name`, `parent_folder_id`, `created_at`

`document_tags`
- `id`, `name`

`document_tag_map`
- `id`, `document_id`, `tag_id`
- unique on `(document, tag)`

### Conversations

`conversations`
- `id`, `case_id`
- `title`, `started_at`, `last_message_at`

`messages`
- `id`, `conversation_id`
- `role`, `content`, `created_at`

`citations`
- `id`, `message_id`
- `source_type`, `document_id`, `email_id`, `chunk_id`
- `citation_text`, `created_at`

### Email / Gmail

`gmail_credentials`
- `id`
- `email_address`, `access_token`, `refresh_token`
- `token_expiry`, `scope`, `is_active`
- `created_at`, `updated_at`

`emails`
- `id`
- `gmail_message_id`, `gmail_thread_id`
- `case_id`, `subject`, `sender`, `recipients`
- `sent_at`, `body_text`, `has_attachments`, `created_at`

`email_attachments`
- `id`, `email_id`, `document_id`
- `filename`, `file_path`, `gmail_attachment_id`, `created_at`

### Tagging

`case_tags`
- `id`, `name`

`case_tag_map`
- `id`, `case_id`, `tag_id`
- unique on `(case, tag)`

## Framework Tables

### Django built-ins

- `auth_group`
- `auth_group_permissions`
- `auth_permission`
- `auth_user`
- `auth_user_groups`
- `auth_user_user_permissions`
- `django_admin_log`
- `django_content_type`
- `django_migrations`
- `django_session`

### Celery support tables

- `django_celery_beat_clockedschedule`
- `django_celery_beat_crontabschedule`
- `django_celery_beat_intervalschedule`
- `django_celery_beat_periodictask`
- `django_celery_beat_periodictasks`
- `django_celery_beat_solarschedule`
- `django_celery_results_chordcounter`
- `django_celery_results_groupresult`
- `django_celery_results_taskresult`

## Schema Notes

- `gmail_credentials` and `hearings` are real migrated tables, added by `0003_gmailcredential_hearing`.
- `DocumentChunk.embedding` is fixed at 768 dimensions in the model, matching `nomic-embed-text`.
- The current schema does not include planning-doc tables such as `fetch_job`.
- There is no `Party` model or table in the current `core/models/` package.

## Dev Database Snapshot

Verified counts for the disputed feature areas:

- `hearings`: `0`
- `gmail_credentials`: `1`
- `emails`: `49`
- `activity_logs`: `0`
