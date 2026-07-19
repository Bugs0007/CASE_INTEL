"""
Document views — list, retrieve, upload, and process documents.
"""

import logging

from django.core.files.storage import default_storage
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db.models import Prefetch

from core.models import Case, Document, ProcessingJob
from core.serializers import DocumentSerializer, DocumentUploadSerializer


def _with_latest_jobs(qs):
    """Prefetch processing jobs newest-first so DocumentSerializer can
    expose the latest job's status/progress without N+1 queries."""
    return qs.prefetch_related(
        Prefetch(
            "processing_jobs",
            queryset=ProcessingJob.objects.order_by("-created_at"),
        )
    )

logger = logging.getLogger(__name__)


class DocumentListView(generics.ListAPIView):
    """List documents, optionally filtered by case_id and/or processing_status.

    GET /api/documents/
    GET /api/documents/?case_id=1
    GET /api/documents/?processing_status=failed
    """

    serializer_class = DocumentSerializer

    def get_queryset(self):
        qs = _with_latest_jobs(Document.objects.select_related("case"))
        case_id = self.request.query_params.get("case_id")
        if case_id is not None:
            qs = qs.filter(case_id=case_id)
        processing_status = self.request.query_params.get("processing_status")
        if processing_status is not None:
            qs = qs.filter(processing_status=processing_status)
        return qs


class DocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a document.

    GET    /api/documents/<id>/
    PATCH  /api/documents/<id>/
    DELETE /api/documents/<id>/
    """

    serializer_class = DocumentSerializer
    queryset = _with_latest_jobs(Document.objects.select_related("case"))


class DocumentUploadView(APIView):
    """Upload a document file and trigger processing.

    POST /api/documents/upload/  (multipart/form-data)
    Fields:
        file          - the document file
        case_id       - optional case to associate with
        document_type - optional type classification
    """

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request: Request) -> Response:
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]
        case_id = serializer.validated_data.get("case_id")
        document_type = serializer.validated_data.get("document_type", "other")

        # Validate case exists when provided
        if case_id is not None and not Case.objects.filter(id=case_id).exists():
            return Response(
                {"detail": f"Case with id {case_id} does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Determine file type from extension
        filename = uploaded_file.name
        file_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        # Save via the configured storage backend (local disk or S3 -- see
        # STORAGES in settings.py). default_storage.save() already avoids
        # overwriting an existing name, on both backends.
        saved_name = default_storage.save(f"documents/{filename}", uploaded_file)

        # Create document record
        document = Document.objects.create(
            case_id=case_id,
            filename=filename,
            file_path=saved_name,
            file_type=file_type,
            file_size=uploaded_file.size,
            document_type=document_type,
            processing_status="pending",
        )

        # Enqueue background processing immediately -- the worker
        # (manage.py process_jobs) picks it up; nothing heavy happens in
        # this request.
        ProcessingJob.enqueue(document)

        logger.info("Document uploaded and queued: id=%d, filename=%s", document.id, filename)

        return Response(
            DocumentSerializer(document).data,
            status=status.HTTP_201_CREATED,
        )


class DocumentProcessView(APIView):
    """Enqueue processing for a document (extract text, OCR if scanned,
    chunk, embed) and return immediately.

    The actual work happens in the `manage.py process_jobs` background
    worker -- this endpoint never blocks on extraction/embedding. Also the
    retry path: POSTing for a failed document simply enqueues a fresh job.

    POST /api/documents/<id>/process/
    """

    def post(self, request: Request, pk: int) -> Response:
        try:
            document = Document.objects.get(id=pk)
        except Document.DoesNotExist:
            return Response(
                {"detail": "Document not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        job, created = ProcessingJob.enqueue(document)
        if not created:
            return Response(
                {"detail": f"Document is already {job.status} (job {job.id})."},
                status=status.HTTP_409_CONFLICT,
            )

        logger.info("Document %d queued for processing (job %d)", pk, job.id)

        document = (
            _with_latest_jobs(Document.objects.select_related("case")).get(id=pk)
        )
        return Response(
            DocumentSerializer(document).data, status=status.HTTP_202_ACCEPTED
        )


class DocumentDownloadView(APIView):
    """Return a URL for downloading/viewing a document's file.

    GET /api/documents/<id>/download/

    Local disk (USE_S3=false): a relative /media/... URL served by Django.
    S3 (USE_S3=true): a short-lived presigned URL -- the bucket blocks all
    public access, so this is the only way to reach the file. Either way,
    reaching this endpoint itself still requires the normal token auth;
    the URL it returns is time-limited on S3, so treat it as sensitive but
    disposable.
    """

    def get(self, request: Request, pk: int) -> Response:
        try:
            document = Document.objects.get(id=pk)
        except Document.DoesNotExist:
            return Response(
                {"detail": "Document not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            url = default_storage.url(document.file_path)
        except Exception as exc:
            logger.exception("Could not generate download URL for document %d", pk)
            return Response(
                {"detail": f"File is unavailable: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({"url": url, "filename": document.filename})
