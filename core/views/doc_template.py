"""Template-merge document generation (core/services/doc_templates/).

Both views resolve the case through OwnerScopedMixin's queryset, so a case
id belonging to another advocate is a 404; the contact must belong to that
same case.
"""

from rest_framework import generics, status
from rest_framework.response import Response

from core.models import Case
from core.serializers import DocumentSerializer
from core.services import doc_templates
from core.services.invoice_service import get_or_create_profile
from core.views.mixins import OwnerScopedMixin


def _int_or_none(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


class DocTemplateListView(OwnerScopedMixin, generics.GenericAPIView):
    """GET /api/doc-templates/
    GET /api/doc-templates/?case=<id>[&contact=<id>]

    Without a case: the available templates. With one: each template's
    fields as they'd be filled for that case -- the value and where it came
    from, and which required ones are still missing (and where to fix them).
    """

    queryset = Case.objects.all()

    def get(self, request, *args, **kwargs):
        templates = doc_templates.list_templates()
        case_id = _int_or_none(request.query_params.get("case"))
        if request.query_params.get("case") and case_id is None:
            return Response({"detail": "case must be an id."}, status=status.HTTP_400_BAD_REQUEST)

        if case_id is None:
            return Response(
                [
                    {"key": t.key, "title": t.title, "description": t.description}
                    for t in templates
                ]
            )

        case = self.get_queryset().filter(id=case_id).first()
        if case is None:
            return Response({"detail": "Case not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            contact = doc_templates.pick_contact(case, _int_or_none(request.query_params.get("contact")))
        except doc_templates.InvalidContactError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        profile = get_or_create_profile(request.user)
        rows = []
        for t in templates:
            resolution = doc_templates.resolve(t, case=case, profile=profile, contact=contact)
            rows.append(
                {
                    "key": t.key,
                    "title": t.title,
                    "description": t.description,
                    "contact_id": contact.id if contact else None,
                    "fields": [f.as_dict() for f in resolution.fields],
                    "ready": not resolution.missing,
                }
            )
        return Response(rows)


class CaseGenerateDocumentView(OwnerScopedMixin, generics.GenericAPIView):
    """POST /api/cases/<id>/generate-document/
        {"template": "vakalatnama", "contact_id": 3, "inputs": {"place": "Hyderabad"}}

    201 with the new Document. 400 with code "missing_fields" and the list
    of what's missing when a required field is still empty -- nothing is
    saved in that case.
    """

    queryset = Case.objects.all()

    def post(self, request, *args, **kwargs):
        case = self.get_object()
        template_key = request.data.get("template")
        if not template_key:
            return Response({"template": ["Choose a template."]}, status=status.HTTP_400_BAD_REQUEST)
        inputs = request.data.get("inputs") or {}
        if not isinstance(inputs, dict):
            return Response({"inputs": ["Expected an object of field: value."]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            document = doc_templates.generate_document(
                case,
                template_key,
                profile=get_or_create_profile(request.user),
                contact_id=_int_or_none(request.data.get("contact_id")),
                inputs=inputs,
            )
        except doc_templates.MissingFieldsError as exc:
            return Response(
                {"detail": str(exc), "code": "missing_fields", "missing": exc.missing},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except doc_templates.DocTemplateError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            DocumentSerializer(document, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )
