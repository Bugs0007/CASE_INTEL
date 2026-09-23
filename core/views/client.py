"""Clients (billing entities), their outstanding statements, and the
billing portfolio across every case.

Every view here uses OwnerScopedMixin: the statement and portfolio are
computed only from get_queryset(), which is already filtered to
request.user, so another advocate's clients, fees and hearings are never in
reach.
"""

from django.db.models import Count
from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import generics
from rest_framework.response import Response

from core.models import AppearanceFee, Client, Hearing
from core.serializers.client import ClientSerializer
from core.services import billing_portfolio
from core.services.invoice_service import get_or_create_profile
from core.views.mixins import OwnerScopedMixin


class ClientListCreateView(OwnerScopedMixin, generics.ListCreateAPIView):
    """GET/POST /api/clients/ -- ?search= filters by name."""

    serializer_class = ClientSerializer

    def get_base_queryset(self):
        qs = Client.objects.annotate(case_count=Count("cases"))
        search = (self.request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class ClientDetailView(OwnerScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/clients/<id>/

    Deleting a client never deletes its cases: Case.client is SET_NULL, so
    they simply become unassigned again.
    """

    serializer_class = ClientSerializer
    queryset = Client.objects.annotate(case_count=Count("cases"))


class ClientStatementPdfView(OwnerScopedMixin, generics.GenericAPIView):
    """GET /api/clients/<id>/statement/pdf/

    A separate path, not ?format=pdf -- DRF swallows a `format` query
    parameter as a renderer override and 404s before the view runs.
    """

    queryset = Client.objects.all()

    def get(self, request, *args, **kwargs):
        client = self.get_object()
        fees = AppearanceFee.objects.filter(owner=request.user)
        pdf = billing_portfolio.render_client_statement_pdf(
            client, fees, get_or_create_profile(request.user)
        )
        filename = f"statement-{slugify(client.name) or client.id}-{timezone.localdate():%Y%m%d}.pdf"
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response


class BillingPortfolioView(OwnerScopedMixin, generics.GenericAPIView):
    """GET /api/billing/portfolio/

    Aging of unpaid invoices (0-30 / 31-60 / 61-90 / 90+ days), outstanding
    per client (plus cases with no client yet), and this month's hearings
    that haven't been billed. List payloads are capped (see
    billing_portfolio.MAX_ROWS) with the true totals alongside.
    """

    queryset = AppearanceFee.objects.all()

    def get(self, request, *args, **kwargs):
        hearings = Hearing.objects.filter(owner=request.user)
        return Response(billing_portfolio.portfolio(self.get_queryset(), hearings))
