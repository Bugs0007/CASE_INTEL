"""Case assistant: approval, outputs (DOCX, case note), download, case notes.

Plain APIViews, owner-scoped by hand. Approve and outputs answer 404 while
settings.CASE_DRAFTING_ENABLED is off. The download and the case-notes
list/delete stay available: switching drafting off must not hide what was
already approved and saved.
"""

from django.conf import settings
from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Case, CaseNote, DraftOutput
from core.serializers.case_assistant import (
    case_note_payload,
    draft_detail,
    draft_queryset,
    output_payload,
)
from core.services.drafting import approval, outputs


class _DraftingEnabledView(APIView):
    """404 for every method while drafting is off (after authentication, so
    an anonymous caller still gets 401)."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not getattr(settings, "CASE_DRAFTING_ENABLED", False):
            raise NotFound()


def _int_field(data, name):
    value = data.get(name) if isinstance(data, dict) else None
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _conflict(exc: approval.DraftConflict) -> Response:
    return Response(
        {"detail": exc.detail, "code": exc.code, **exc.extra}, status=exc.status
    )


class DraftApproveView(_DraftingEnabledView):
    """POST /api/case-assistant/drafts/<id>/approve/"""

    def post(self, request: Request, pk: int) -> Response:
        revision_id = _int_field(request.data, "revision_id")
        if revision_id is None:
            return Response(
                {"detail": "revision_id is required."}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            approval.approve_revision(
                draft_id=pk,
                revision_id=revision_id,
                user=request.user,
                acknowledge_open_items=request.data.get("acknowledge_open_items") is True,
            )
        except approval.DraftNotFound:
            raise NotFound()
        except approval.DraftConflict as exc:
            return _conflict(exc)
        draft = draft_queryset().get(owner=request.user, pk=pk)
        return Response(draft_detail(draft))


class DraftOutputCreateView(_DraftingEnabledView):
    """POST /api/case-assistant/drafts/<id>/outputs/"""

    def post(self, request: Request, pk: int) -> Response:
        revision_id = _int_field(request.data, "revision_id")
        destination = request.data.get("destination") if isinstance(request.data, dict) else None
        if revision_id is None or destination not in (
            DraftOutput.DEST_DOCX,
            DraftOutput.DEST_CASE_NOTE,
        ):
            return Response(
                {"detail": "revision_id and a destination of docx or case_note are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            output, created = outputs.create_output(
                draft_id=pk,
                revision_id=revision_id,
                user=request.user,
                destination=destination,
            )
        except approval.DraftNotFound:
            raise NotFound()
        except approval.DraftConflict as exc:
            return _conflict(exc)
        except outputs.OutputStorageError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(
            output_payload(output),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class DraftOutputDownloadView(APIView):
    """GET /api/case-assistant/outputs/<id>/download/

    The file itself, never a storage URL or path.
    """

    def get(self, request: Request, pk: int) -> HttpResponse:
        output = DraftOutput.objects.filter(
            owner=request.user,
            pk=pk,
            destination=DraftOutput.DEST_DOCX,
            status=DraftOutput.STATUS_READY,
        ).first()
        data = outputs.read_docx(output) if output is not None else None
        if data is None:
            raise NotFound()
        response = HttpResponse(data, content_type=outputs.DOCX_CONTENT_TYPE)
        response["Content-Disposition"] = f'attachment; filename="{output.filename}"'
        response["Cache-Control"] = "private, no-store"
        return response


class CaseNoteListView(APIView):
    """GET /api/cases/<case_id>/notes/"""

    def get(self, request: Request, case_id: int) -> Response:
        if not Case.objects.filter(owner=request.user, pk=case_id).exists():
            raise NotFound()
        notes = (
            CaseNote.objects.filter(owner=request.user, case_id=case_id)
            .select_related("origin_revision")
            .order_by("-created_at", "-id")[:100]
        )
        return Response([case_note_payload(note) for note in notes])


class CaseNoteDetailView(APIView):
    """DELETE /api/case-notes/<id>/"""

    def delete(self, request: Request, pk: int) -> Response:
        deleted, _ = CaseNote.objects.filter(owner=request.user, pk=pk).delete()
        if not deleted:
            raise NotFound()
        return Response(status=status.HTTP_204_NO_CONTENT)
