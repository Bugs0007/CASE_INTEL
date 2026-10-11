"""The hcservices.ecourts.gov.in flow shared by every High Court adapter.

    POST cases_qry/index_qry.php  action_code=showCauseList  flag=civ_t ...
        -> HTML index (table.causelistTbl): Sr No | Bench | Cause List Type | View
    GET  cases/display_causelist_pdf.php?filename=<token>   (same session!)
        -> the PDF, or the 21-byte `Order not uploaded`

Why this is not bharat_courts' own HCServicesClient.cause_list():
  * it joins the PDF URL wrongly ("<base>/cases_qry/cases/..." -> 404);
  * its CAPTCHA retry only recognises the QUOTED string "Invalid Captcha",
    so the portal's real failure bodies (`Invalid Captcha`, and
    `{"Error":"ERROR_VAL"}` for an empty CAPTCHA) come back as successes;
  * it never looks at the PDFs.
Only its transport and CAPTCHA solver are reused (`_init_session`,
`_solve_captcha`, `_http`).

`flag=civ_t` is the only flag sent: the live probe of 2026-10-10 got the
identical index from `cri_t` on all 16 benches tried (Telangana's earlier
"cri_t returns nothing" no longer holds).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

from ..base import RawDoc
from ..exceptions import CauseListCaptchaError, CauseListFetchError
from ..fetchlib import (
    INDEX_CAPTCHA_FAILED,
    INDEX_TABLE,
    Pacer,
    classify_hcservices_index,
    download_pdf,
    safe_name,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexRow:
    serial: str
    bench_label: str
    list_type: str
    href: str
    doc_key: str = ""


def pdf_url(href: str) -> str:
    """Absolute URL for a 'View Causelist' link (the corrected join)."""
    from bharat_courts.hcservices import endpoints

    base = endpoints.BASE_URL.rstrip("/")
    href = (href or "").strip()
    if not href:
        return ""
    if href.startswith(("http://", "https://")):
        return href
    return f"{base}/{href.lstrip('/')}"


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_index_rows(html: str) -> list[IndexRow]:
    """Rows of the index table that carry a PDF link.

    Each row gets a stable `doc_key`: a hash of (bench, list type, nth row
    with that pair). The portal's own `filename=` token is encrypted and
    not guaranteed stable across sessions, so it is not used.
    """
    text = (html or "").strip().lstrip("﻿")
    soup = BeautifulSoup(text, "lxml")
    table = soup.find("table", class_="causelistTbl") or soup.find("table")
    if table is None:
        return []
    rows: list[IndexRow] = []
    seen: dict[tuple[str, str], int] = {}
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 4:
            continue
        link = cells[3].find("a", href=True)
        if link is None:
            continue
        bench = _collapse(cells[1].get_text(" "))
        list_type = _collapse(cells[2].get_text(" "))
        n = seen.get((bench, list_type), 0)
        seen[(bench, list_type)] = n + 1
        key = hashlib.sha1(f"{bench}|{list_type}|{n}".encode()).hexdigest()[:16]
        rows.append(
            IndexRow(
                serial=_collapse(cells[0].get_text()),
                bench_label=bench,
                list_type=list_type,
                href=link["href"].strip(),
                doc_key=key,
            )
        )
    return rows


async def fetch_index(
    client,
    *,
    state_code: str,
    bench_code: str,
    list_date: date,
    pacer: Pacer,
    today: date,
    attempts: int = 5,
    flag: str = "civ_t",
) -> tuple[str, list[IndexRow], str]:
    """(kind, rows, detail). kind: table | none_available | captcha_failed | other.

    Each attempt is a fresh session (the portal pins a CAPTCHA to a session),
    and an unreadable CAPTCHA is never submitted -- submitting '' is exactly
    what produces ERROR_VAL.
    """
    from bharat_courts.hcservices import endpoints

    selprevdays = "1" if list_date < today else "0"
    causelist_date = list_date.strftime("%d-%m-%Y")
    last_detail = ""
    for attempt in range(1, attempts + 1):
        await pacer.wait()
        await client._init_session()
        captcha = await client._solve_captcha()
        if not captcha or len(captcha) < 4:
            last_detail = "CAPTCHA not readable"
            logger.info("hcservices CAPTCHA unreadable (attempt %d/%d)", attempt, attempts)
            continue
        form = endpoints.cause_list_form(
            state_code=state_code,
            court_code=bench_code,
            captcha=captcha,
            causelist_date=causelist_date,
            flag=flag,
            selprevdays=selprevdays,
        )
        resp = await client._http.post(
            endpoints.INDEX_QRY_URL,
            data=form,
            headers={"Referer": endpoints.MAIN_PAGE_URL},
        )
        kind, detail = classify_hcservices_index(resp.text)
        if kind == INDEX_CAPTCHA_FAILED:
            last_detail = detail
            logger.info("hcservices CAPTCHA rejected (attempt %d/%d): %s", attempt, attempts, detail)
            continue
        if kind == INDEX_TABLE:
            rows = parse_index_rows(resp.text)
            if not rows:
                return "other", [], "index table without any PDF link"
            return INDEX_TABLE, rows, ""
        return kind, [], detail
    return INDEX_CAPTCHA_FAILED, [], last_detail


async def download_docs(
    client,
    rows: list[IndexRow],
    workdir: Path,
    *,
    pacer: Pacer,
    deadline: float,
    tag: str = "",
) -> list[RawDoc]:
    """Fetch every index row's PDF into `workdir`, in the index's session.

    Anything not obtained comes back as a RawDoc with a non-ok status, so
    the caller can count it: a document we don't have is a document the case
    might be in.
    """
    docs: list[RawDoc] = []
    for n, row in enumerate(rows):
        url = pdf_url(row.href)
        doc = RawDoc(
            doc_key=f"{tag}{row.doc_key}",
            status="fetch_error",
            list_type=row.list_type,
            bench_label=row.bench_label,
            source_ref=url,
            source_public=False,  # hcservices PDF links are session-bound
        )
        if time.monotonic() > deadline:
            doc.error = "per-target time budget exhausted"
            docs.append(doc)
            continue
        dest = workdir / f"{tag}{n:03d}_{safe_name(row.list_type, 24)}.pdf"
        try:
            got = await download_pdf(client._http, url, dest, pacer=pacer)
        except (CauseListFetchError, asyncio.TimeoutError) as exc:
            doc.error = str(exc)[:300]
            docs.append(doc)
            continue
        if got.kind == "pdf":
            doc.status, doc.path, doc.sha256, doc.size = "ok", dest, got.sha256, got.size
        elif got.kind == "not_uploaded":
            doc.status = "not_uploaded"
        else:
            doc.error = f"unexpected body: {got.preview[:80]!r}"
        docs.append(doc)
    return docs


def captcha_failed_error(detail: str) -> CauseListCaptchaError:
    return CauseListCaptchaError(f"CAPTCHA budget exhausted ({detail})")
