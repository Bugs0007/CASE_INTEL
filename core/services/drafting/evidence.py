"""What the server collects for one draft: the evidence a block may cite.

Every entry is a DraftEvidence dict (frontend-next/types/draft.ts):

    {id, kind, label, ref, fingerprint}

IDs: case:<id>, hearing:<id>, task:<id>, event:<id>,
doc:<document_id>:c<chunk_id>.

`fingerprint` is a short sha256 of the fact's canonical values, so approval
can later recollect and see whether a fact changed. Evidence entries carry
IDs and short labels only; the text a model reads (`facts`, `excerpts`) is
returned next to them and is never stored on a revision.

Every query here filters by the owner AND the case. Document chunks are read
only for the document ids the advocate selected, after each one is verified
as the owner's document on this case.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Iterable, Optional

from django.db.models import Case as SqlCase
from django.db.models import IntegerField, Value, When

from core.models import Case, Document, DocumentChunk, Hearing
from core.services.practice_assistant import reads

MAX_HEARINGS = 10
MAX_TASKS = 15
MAX_EVENTS = 10  # case_facts carries at most reads.CASE_FACTS_ROWS (10)
MAX_CHUNKS = 8
MAX_EXCERPT_CHARS = 1200
MAX_OUTCOME_CHARS = 300
MAX_KEYWORDS = 8

MISSING_NEXT_HEARING = "No next hearing date is recorded."
MISSING_COURT = "No court is recorded for this case."
MISSING_PARTIES = "The parties are not recorded for this case."

WARNING_TASKS_TRUNCATED = "Only the first open tasks were used. The case has more."
WARNING_EVENTS_TRUNCATED = "Only the first upcoming appointments were used. The case has more."
WARNING_DOCUMENT_NO_TEXT = "A selected document has no readable text and was not used."


class SourceUnavailable(Exception):
    """A selected source document is not the owner's document on this case."""


def fingerprint(values) -> str:
    canonical = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _entry(kind: str, evidence_id: str, ref: dict, values) -> dict:
    return {
        "id": evidence_id,
        "kind": kind,
        "label": ref["label"],
        "ref": ref,
        "fingerprint": fingerprint(values),
    }


def _hearing_fact(entry: dict, outcome: str = "") -> tuple[dict, str]:
    values = {k: entry[k] for k in ("day", "start_time", "status", "label")}
    values["outcome"] = outcome
    when = entry["day"] + (f" {entry['start_time']}" if entry["start_time"] else "")
    text = f"Hearing on {when}, status {entry['status']}: {entry['label']}."
    if outcome:
        text += f" Recorded outcome: {outcome}"
    return _entry("hearing", f"hearing:{entry['id']}", entry["ref"], values), text


def collect_case_evidence(*, owner, case_id: int, now: Optional[datetime] = None) -> Optional[dict]:
    """Recorded facts of one of the owner's cases, or None when the case is
    not the owner's.

    Returns {evidence, facts, missing_facts, warnings}. `facts` is a list of
    {id, text} lines for the prompt, one per evidence entry, in the same
    order. `missing_facts` is decided here from the stored rows, never by a
    model.
    """
    found = reads.case_facts(owner=owner, case_id=case_id, now=now)
    if found is None:
        return None
    case = found["case"]
    parties = (
        Case.objects.filter(owner=owner, pk=case_id)
        .values("petitioner_name", "respondent_name", "client_name", "opposing_party", "user_party_role")
        .first()
    ) or {}

    evidence: list[dict] = []
    facts: list[dict] = []
    missing: list[str] = []
    warnings: list[str] = []

    def add(entry: dict, text: str) -> None:
        evidence.append(entry)
        facts.append({"id": entry["id"], "text": text})

    petitioner = (parties.get("petitioner_name") or "").strip()
    respondent = (parties.get("respondent_name") or "").strip()
    client = (parties.get("client_name") or "").strip()
    opposing = (parties.get("opposing_party") or "").strip()
    role = parties.get("user_party_role") or "unknown"
    case_values = {
        "title": case["title"],
        "case_number": case["case_number"],
        "cnr_number": case["cnr_number"],
        "court": case["court"],
        "status": case["status"],
        "petitioner": petitioner,
        "respondent": respondent,
        "client": client,
        "opposing_party": opposing,
        "user_party_role": role,
    }
    lines = [f"Case: {case['title']}.", f"Status: {case['status']}."]
    if case["case_number"]:
        lines.append(f"Case number: {case['case_number']}.")
    if case["cnr_number"]:
        lines.append(f"CNR: {case['cnr_number']}.")
    if case["court"]:
        lines.append(f"Court: {case['court']}.")
    if petitioner:
        lines.append(f"Petitioner: {petitioner}.")
    if respondent:
        lines.append(f"Respondent: {respondent}.")
    if client:
        lines.append(f"Client: {client}.")
    if opposing:
        lines.append(f"Opposing party: {opposing}.")
    if role != "unknown":
        lines.append(f"The advocate appears for the {role}.")
    add(_entry("case", f"case:{case['id']}", case["ref"], case_values), " ".join(lines))

    if not case["court"]:
        missing.append(MISSING_COURT)
    if not (petitioner and respondent) and not (client and opposing):
        missing.append(MISSING_PARTIES)

    next_hearing = found["next_hearing"]
    if next_hearing is None:
        missing.append(MISSING_NEXT_HEARING)
    else:
        entry, text = _hearing_fact(next_hearing)
        add(entry, "Next hearing. " + text)

    current = reads._clock(now)
    recent = Hearing.objects.filter(
        owner=owner, case_id=case_id, case__owner=owner, hearing_date__lt=current
    ).select_related("case").order_by("-hearing_date", "-id")[: MAX_HEARINGS - 1]
    for hearing in recent:
        outcome = " ".join((hearing.outcome or "").split())[:MAX_OUTCOME_CHARS]
        entry, text = _hearing_fact(reads._hearing_entry(hearing), outcome)
        add(entry, "Earlier hearing. " + text)

    deadlines = reads.open_deadlines(owner=owner, case_id=case_id, limit=MAX_TASKS, now=now)
    for row in deadlines["entries"]:
        values = {k: row[k] for k in ("title", "due_date", "status", "kind", "needs_review")}
        due = f"due {row['due_date']}" if row["due_date"] else "no due date recorded"
        text = f"Open task ({row['kind']}), {due}: {row['title']}."
        if row["overdue"]:
            text += " Overdue."
        if row["needs_review"]:
            text += " The due date needs the advocate's review."
        add(_entry("task", f"task:{row['id']}", row["ref"], values), text)
    if deadlines["truncated"]:
        warnings.append(WARNING_TASKS_TRUNCATED)

    events = found["upcoming_events"]
    for row in events["entries"][:MAX_EVENTS]:
        values = {k: row[k] for k in ("day", "start_time", "end_time", "status", "label")}
        when = row["day"] + (f" {row['start_time']}" if row["start_time"] else "")
        add(
            _entry("event", f"event:{row['id']}", row["ref"], values),
            f"Appointment on {when}: {row['label']}.",
        )
    if events["truncated"]:
        warnings.append(WARNING_EVENTS_TRUNCATED)

    return {"evidence": evidence, "facts": facts, "missing_facts": missing, "warnings": warnings}


def _keywords(text: str) -> list[str]:
    seen: list[str] = []
    for word in re.findall(r"[A-Za-z0-9]{4,}", text or ""):
        word = word.lower()
        if word not in seen:
            seen.append(word)
    # Longest first: the more specific words of a short brief.
    return sorted(seen, key=lambda w: (-len(w), w))[:MAX_KEYWORDS]


def collect_document_evidence(
    *, owner, case_id: int, document_ids: Iterable[int], instructions: str = ""
) -> dict:
    """Excerpts from the documents the advocate selected, and only those.

    Every id must be the owner's document on this case, else SourceUnavailable
    (nothing is read). An empty selection reads nothing at all. Chunks are
    ranked by how many words of the instructions they contain, then by
    document and position, so with no match the first chunks are used.

    Returns {evidence, excerpts, warnings}; `excerpts` is a list of
    {id, filename, text} for the prompt.
    """
    wanted = sorted({int(doc_id) for doc_id in document_ids})
    if not wanted:
        return {"evidence": [], "excerpts": [], "warnings": []}

    documents = {
        doc.id: doc
        for doc in Document.objects.filter(owner=owner, case_id=case_id, id__in=wanted).only(
            "id", "case_id", "filename", "document_date"
        )
    }
    if len(documents) != len(wanted):
        raise SourceUnavailable()

    score = Value(0, output_field=IntegerField())
    for word in _keywords(instructions):
        score = score + SqlCase(
            When(chunk_text__icontains=word, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )
    chunks = list(
        DocumentChunk.objects.filter(
            owner=owner,
            document__owner=owner,
            document__case_id=case_id,
            document_id__in=wanted,
        )
        .annotate(match_score=score)
        .order_by("-match_score", "document_id", "chunk_index", "id")
        .only("id", "document_id", "chunk_index", "chunk_text")[:MAX_CHUNKS]
    )

    evidence: list[dict] = []
    excerpts: list[dict] = []
    for chunk in chunks:
        document = documents[chunk.document_id]
        text = (chunk.chunk_text or "")[:MAX_EXCERPT_CHARS]
        evidence_id = f"doc:{document.id}:c{chunk.id}"
        ref = {
            "kind": "document",
            "id": document.id,
            "case_id": document.case_id,
            "label": document.filename,
            "recorded_at": document.document_date.isoformat() if document.document_date else None,
        }
        evidence.append(
            _entry(
                "document",
                evidence_id,
                ref,
                {"document_id": document.id, "chunk_index": chunk.chunk_index, "text": text},
            )
        )
        excerpts.append({"id": evidence_id, "filename": document.filename, "text": text})

    warnings: list[str] = []
    if set(wanted) - {chunk.document_id for chunk in chunks} and len(chunks) < MAX_CHUNKS:
        warnings.append(WARNING_DOCUMENT_NO_TEXT)
    return {"evidence": evidence, "excerpts": excerpts, "warnings": warnings}
