"""Shared helpers for the cause-list tests.

`StaticAdapter` stands in for a portal: it hands the service a prepared set
of documents (real fixture files, copied into the service's temp dir, since
the service deletes each document once read) and parses them with whatever
parser the test is exercising. Everything downstream of `adapter.fetch` --
parsing, matching, the not_listed rule, the writes -- is the real code.
"""

from __future__ import annotations

import datetime
import pathlib
import shutil

from django.utils import timezone

from core.models import Case, Hearing
from core.services.causelists import base

FIXTURES_ROOT = pathlib.Path(__file__).parent / "fixtures" / "causelists"


def make_doc(path, doc_key=None, *, list_type="", bench="", status="ok", error=""):
    path = pathlib.Path(path) if path else None
    return base.RawDoc(
        doc_key=doc_key or (path.name if path else "doc"),
        status=status,
        path=path,
        list_type=list_type,
        bench_label=bench,
        error=error,
        sha256=doc_key or "",
    )


class StaticAdapter(base.CauseListAdapter):
    portal = base.PORTAL_HCSERVICES

    def __init__(
        self,
        key,
        docs,
        parse_fn,
        *,
        status="ok",
        doc_total=None,
        early_exit=False,
        error="",
        court_alias=None,
    ):
        self.key = key
        self.display_name = key
        self._docs = docs
        self._parse_fn = parse_fn
        self._status = status
        self._doc_total = len(docs) if doc_total is None else doc_total
        self._early_exit = early_exit
        self._error = error

    def resolve(self, case):  # pragma: no cover - not used
        raise NotImplementedError

    def fetch(self, target, list_date, workdir):
        out = []
        for doc in self._docs:
            if doc.path is not None and doc.status == "ok":
                copy = pathlib.Path(workdir) / f"{len(out):03d}_{doc.path.name}"
                shutil.copyfile(doc.path, copy)
                doc = base.RawDoc(**{**doc.__dict__, "path": copy})
            out.append(doc)
        return base.FetchResult(
            status=self._status,
            docs=out,
            doc_total=self._doc_total,
            early_exit=self._early_exit,
            error=self._error,
        )

    def parse(self, doc):
        return self._parse_fn(doc)


def make_case(owner, case_number, *, court_type="high_court", tracking_config=None, **extra):
    config = {"court_type": court_type, **(tracking_config or {})}
    return Case.objects.create(
        owner=owner,
        case_number=case_number,
        title=case_number,
        client_name="",
        court_type=court_type,
        tracking_enabled=True,
        tracking_config=config,
        **extra,
    )


def make_hearing(owner, case, day: datetime.date, *, status="scheduled"):
    return Hearing.objects.create(
        owner=owner,
        case=case,
        hearing_date=timezone.make_aware(datetime.datetime(day.year, day.month, day.day, 0, 0)),
        hearing_type="other",
        source="ecourts",
        status=status,
    )


def target_of(adapter, key, params=None):
    return base.ListingTarget(adapter=adapter.key, key=key, label=key, params=params or {})
