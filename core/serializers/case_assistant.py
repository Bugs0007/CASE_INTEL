"""Request validation and plain payload builders for the case-assistant API.

The payload functions return the JSON shapes of frontend-next/types/draft.ts.
Callers prefetch `revisions` (and `revisions__outputs`) to keep query counts
bounded; the functions fall back to a query when nothing was prefetched.
"""
from rest_framework import serializers

from core.models import AssistantDraft
from core.services.drafting import schema

BRIEF_DEFAULTS = {
    "instructions": "",
    "audience": "",
    "tone": "neutral",
    "length": "standard",
    "source_document_ids": [],
}


class DraftCreateSerializer(serializers.Serializer):
    case_id = serializers.IntegerField()
    subtype = serializers.ChoiceField(choices=list(schema.SUBTYPES))
    origin_message_id = serializers.IntegerField(required=False, allow_null=True)
    client_request_id = serializers.CharField(max_length=64)
    instructions = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    audience = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    tone = serializers.ChoiceField(choices=["neutral", "formal", "plain"], required=False, default="neutral")
    length = serializers.ChoiceField(choices=["short", "standard", "detailed"], required=False, default="standard")
    source_document_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, max_length=20, default=list
    )


class RevisionCreateSerializer(serializers.Serializer):
    expected_revision = serializers.IntegerField()
    body = serializers.JSONField()


def _iso(value):
    return value.isoformat() if value else None


def _revisions(draft):
    return list(draft.revisions.all())


def revision_summary(revision) -> dict:
    return {
        "id": revision.id,
        "version": revision.version,
        "source": revision.source,
        "created_at": _iso(revision.created_at),
        "approved_at": _iso(revision.approved_at),
    }


def revision_payload(revision) -> dict:
    return {
        **revision_summary(revision),
        "body": revision.body,
        "schema_version": revision.schema_version,
        "evidence": revision.evidence,
        "missing_facts": revision.missing_facts,
        "warnings": revision.warnings,
        "approved_hash": revision.approved_hash,
    }


def output_payload(output) -> dict:
    return {
        "id": output.id,
        "revision_id": output.revision_id,
        "destination": output.destination,
        "status": output.status,
        "filename": output.filename,
        "case_note_id": output.case_note_id,
        "error": output.error,
        "created_at": _iso(output.created_at),
    }


def case_note_payload(note) -> dict:
    origin = note.origin_revision
    return {
        "id": note.id,
        "case_id": note.case_id,
        "title": note.title,
        "body": note.body,
        "origin_draft_id": origin.draft_id if origin is not None else None,
        "created_at": _iso(note.created_at),
        "updated_at": _iso(note.updated_at),
    }


def _approved_id(revisions):
    approved = [r for r in revisions if r.approved_at]
    return max(approved, key=lambda r: r.version).id if approved else None


def _base(draft, revisions) -> dict:
    return {
        "id": draft.id,
        "case_id": draft.case_id,
        "kind": draft.kind,
        "subtype": draft.subtype,
        "status": draft.status,
        "approved_revision_id": _approved_id(revisions),
        "created_at": _iso(draft.created_at),
        "updated_at": _iso(draft.updated_at),
    }


def draft_summary(draft) -> dict:
    revisions = _revisions(draft)
    current = next((r for r in revisions if r.id == draft.current_revision_id), None)
    return {
        **_base(draft, revisions),
        "title": (current.body.get("title", "") if current else ""),
        "current_version": current.version if current else None,
    }


def draft_detail(draft) -> dict:
    revisions = _revisions(draft)
    current = next((r for r in revisions if r.id == draft.current_revision_id), None)
    outputs = [o for r in revisions for o in r.outputs.all()]
    outputs.sort(key=lambda o: (o.created_at, o.id))
    brief = {**BRIEF_DEFAULTS, **(draft.brief or {})}
    return {
        **_base(draft, revisions),
        "case_title": draft.case.title,
        "error": draft.error,
        "generation": draft.generation,
        "brief": brief,
        "current_revision": revision_payload(current) if current else None,
        "revisions": [revision_summary(r) for r in revisions],
        "outputs": [output_payload(o) for o in outputs],
    }


def draft_queryset():
    """Owner-agnostic base queryset with everything draft_detail reads."""
    return AssistantDraft.objects.select_related("case").prefetch_related(
        "revisions", "revisions__outputs"
    )
