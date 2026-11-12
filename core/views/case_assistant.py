"""Draft storage API under /api/case-assistant/.

Plain APIViews scoped by hand: the owner of every read and write is
`request.user`; case, document, message and draft IDs are resolved under the
owner and answer 404 when they are not the caller's. Every route answers 404
while settings.CASE_DRAFTING_ENABLED is off.
"""
import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import (
    AssistantDraft,
    AssistantDraftRevision,
    Case,
    Document,
    Message,
    ProcessingJob,
)
from core.serializers.case_assistant import (
    BRIEF_DEFAULTS,
    DraftCreateSerializer,
    RevisionCreateSerializer,
    draft_detail,
    draft_queryset,
    draft_summary,
    revision_payload,
)
from core.services.drafting import schema

logger = logging.getLogger(__name__)

MAX_PENDING_DRAFTS = 3
LIST_LIMIT = 50


def _error(http_status, code, detail, **extra):
    return Response({"detail": detail, "code": code, **extra}, status=http_status)


def _limit_reached(owner) -> bool:
    return (
        AssistantDraft.objects.filter(
            owner=owner, status__in=AssistantDraft.PENDING_STATUSES
        ).count()
        >= MAX_PENDING_DRAFTS
    )


def _limit_response():
    return _error(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "draft_limit",
        "Too many drafts are still being prepared. Wait for one to finish and try again.",
    )


def _detail_response(draft_id, owner, http_status):
    draft = draft_queryset().get(pk=draft_id, owner=owner)
    return Response(draft_detail(draft), status=http_status)


class _CaseAssistantView(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not getattr(settings, "CASE_DRAFTING_ENABLED", False):
            raise NotFound()

    def get_draft(self, request, pk):
        try:
            return draft_queryset().get(pk=pk, owner=request.user)
        except AssistantDraft.DoesNotExist:
            raise NotFound()


class DraftListCreateView(_CaseAssistantView):
    def get(self, request):
        raw = request.query_params.get("case_id")
        if not raw or not raw.isdigit():
            return _error(status.HTTP_400_BAD_REQUEST, "invalid_request", "case_id is required.")
        if not Case.objects.filter(pk=int(raw), owner=request.user).exists():
            raise NotFound()
        drafts = draft_queryset().filter(owner=request.user, case_id=int(raw)).order_by(
            "-created_at", "-id"
        )[:LIST_LIMIT]
        return Response([draft_summary(d) for d in drafts])

    def post(self, request):
        ser = DraftCreateSerializer(data=request.data)
        if not ser.is_valid():
            return _error(
                status.HTTP_400_BAD_REQUEST, "invalid_request",
                "The draft request is not valid.", errors=ser.errors,
            )
        data = ser.validated_data
        owner = request.user

        try:
            case = Case.objects.get(pk=data["case_id"], owner=owner)
        except Case.DoesNotExist:
            raise NotFound()

        doc_ids = list(dict.fromkeys(data["source_document_ids"]))
        if doc_ids and (
            Document.objects.filter(owner=owner, case=case, pk__in=doc_ids).count()
            != len(doc_ids)
        ):
            raise NotFound()

        origin_message = None
        if data.get("origin_message_id") is not None:
            try:
                origin_message = Message.objects.select_related("conversation").get(
                    pk=data["origin_message_id"], owner=owner
                )
            except Message.DoesNotExist:
                raise NotFound()

        subtype = data["subtype"]
        brief = {
            **BRIEF_DEFAULTS,
            "instructions": data["instructions"],
            "audience": data["audience"],
            "tone": data["tone"],
            "length": data["length"],
            "source_document_ids": doc_ids,
        }
        origin_message_id = origin_message.id if origin_message else None
        request_id = data["client_request_id"]

        def replay():
            existing = AssistantDraft.objects.filter(
                owner=owner, client_request_id=request_id
            ).first()
            if existing is None:
                return None
            same = (
                existing.case_id == case.id
                and existing.subtype == subtype
                and existing.brief == brief
                and existing.origin_message_id == origin_message_id
            )
            if not same:
                return _error(
                    status.HTTP_409_CONFLICT, "request_mismatch",
                    "That request ID was already used for a different draft.",
                )
            return _detail_response(existing.id, owner, status.HTTP_200_OK)

        replayed = replay()
        if replayed is not None:
            return replayed
        if _limit_reached(owner):
            return _limit_response()

        try:
            with transaction.atomic():
                draft = AssistantDraft.objects.create(
                    owner=owner,
                    case=case,
                    kind=AssistantDraft.KIND_FOR_SUBTYPE[subtype],
                    subtype=subtype,
                    brief=brief,
                    origin_message=origin_message,
                    origin_conversation=origin_message.conversation if origin_message else None,
                    client_request_id=request_id,
                )
                job, _ = ProcessingJob.enqueue_draft_generation(draft)
                draft.job = job
                draft.save(update_fields=["job", "updated_at"])
        except IntegrityError:
            replayed = replay()
            if replayed is None:
                raise
            return replayed

        logger.info("draft %s queued job %s", draft.id, job.id)
        return _detail_response(draft.id, owner, status.HTTP_202_ACCEPTED)


class DraftDetailView(_CaseAssistantView):
    def get(self, request, pk):
        return Response(draft_detail(self.get_draft(request, pk)))


class DraftRevisionDetailView(_CaseAssistantView):
    def get(self, request, pk, version):
        draft = self.get_draft(request, pk)
        for revision in draft.revisions.all():
            if revision.version == version:
                return Response(revision_payload(revision))
        raise NotFound()


class DraftRevisionCreateView(_CaseAssistantView):
    """A draft that is not ready (queued, generating or failed) has no
    current revision to edit from, so a save answers 409 `not_ready`."""

    def post(self, request, pk):
        ser = RevisionCreateSerializer(data=request.data)
        if not ser.is_valid():
            return _error(
                status.HTTP_400_BAD_REQUEST, "invalid_request",
                "The revision request is not valid.", errors=ser.errors,
            )
        expected = ser.validated_data["expected_revision"]
        body = ser.validated_data["body"]
        owner = request.user

        with transaction.atomic():
            try:
                draft = AssistantDraft.objects.select_for_update().get(pk=pk, owner=owner)
            except AssistantDraft.DoesNotExist:
                raise NotFound()
            current = (
                AssistantDraftRevision.objects.filter(pk=draft.current_revision_id).first()
                if draft.current_revision_id
                else None
            )
            if draft.status != AssistantDraft.STATUS_READY or current is None:
                return _error(
                    status.HTTP_409_CONFLICT, "not_ready",
                    "This draft is not ready to edit.",
                )
            if expected != current.id:
                return _error(
                    status.HTTP_409_CONFLICT, "stale_revision",
                    "This draft changed since you opened it. Reload it and try again.",
                    current_revision_id=current.id,
                )
            try:
                schema.validate_body(
                    body, allowed_evidence={e["id"] for e in current.evidence}
                )
                if body.get("subtype") != draft.subtype:
                    raise schema.DraftValidationError(["subtype cannot change"])
            except schema.DraftValidationError as exc:
                return _error(
                    status.HTTP_400_BAD_REQUEST, "invalid_body",
                    "The edited draft is not valid.", errors=exc.errors,
                )
            if body == current.body:
                created = False
            else:
                revision = AssistantDraftRevision.objects.create(
                    owner=owner,
                    draft=draft,
                    version=current.version + 1,
                    body=body,
                    schema_version=schema.SCHEMA_VERSION,
                    evidence=current.evidence,
                    missing_facts=current.missing_facts,
                    warnings=body.get("warnings", []),
                    source=AssistantDraftRevision.SOURCE_EDITED,
                )
                draft.current_revision = revision
                draft.save(update_fields=["current_revision", "updated_at"])
                created = True
        return _detail_response(
            draft.id, owner, status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class DraftRetryView(_CaseAssistantView):
    def post(self, request, pk):
        owner = request.user
        with transaction.atomic():
            try:
                draft = AssistantDraft.objects.select_for_update().get(pk=pk, owner=owner)
            except AssistantDraft.DoesNotExist:
                raise NotFound()
            if draft.status in AssistantDraft.PENDING_STATUSES:
                return _detail_response(draft.id, owner, status.HTTP_200_OK)
            if draft.status != AssistantDraft.STATUS_FAILED:
                return _error(
                    status.HTTP_409_CONFLICT, "not_retryable",
                    "Only a failed draft can be retried.",
                )
            if _limit_reached(owner):
                return _limit_response()
            draft.generation += 1
            draft.error = ""
            draft.status = AssistantDraft.STATUS_QUEUED
            job, _ = ProcessingJob.enqueue_draft_generation(draft)
            draft.job = job
            draft.save(update_fields=["generation", "error", "status", "job", "updated_at"])
        logger.info("draft %s retried job %s generation %s", draft.id, job.id, draft.generation)
        return _detail_response(draft.id, owner, status.HTTP_202_ACCEPTED)
