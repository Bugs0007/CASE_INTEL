"""Mechanical document generation: template merge, no LLM.

A template is a JSON file in ./templates/ -- adding one is dropping a file
there, no code change. Each declares:

  fields  -- name, label, required, and an ordered list of `sources` to
             fill it from (see SOURCES below). A field no source can fill
             is taken from the generation request's `inputs`. A typed value
             is saved back to the record only when the request lists the
             field in `save` AND the field has a home (SAVERS below) --
             the dialog's "Save for next time" boxes.
  blocks  -- what to print, top to bottom, with {field} placeholders.

A required field still empty after both passes blocks generation: the
caller gets the list of what's missing and where each one can be filled
in, rather than a half-blank legal document.

Output is a PDF (fpdf2, Latin-1 core fonts -- so English templates only)
saved as a normal Document on the case.
"""

from __future__ import annotations

import hashlib
import json
import logging
import string
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from django.utils.text import slugify

from core.models import ClientContact, Document
from core.services.pdf_utils import draw_letterhead, pdf_safe

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
BLOCK_TYPES = {"title", "center", "heading", "paragraph", "text", "right", "parties", "signature", "spacer"}
MAX_INPUT_LENGTH = 5000


class DocTemplateError(Exception):
    """Base for generation failures that should surface as a 4xx."""


class UnknownTemplateError(DocTemplateError):
    pass


class InvalidContactError(DocTemplateError):
    pass


class MissingFieldsError(DocTemplateError):
    def __init__(self, missing: list[dict]):
        self.missing = missing
        labels = ", ".join(item["label"] for item in missing)
        super().__init__(f"Fill these in before generating: {labels}.")


@dataclass(frozen=True)
class TemplateField:
    name: str
    label: str
    sources: tuple[str, ...]
    required: bool = True
    multiline: bool = False


@dataclass(frozen=True)
class DocTemplate:
    key: str
    title: str
    description: str
    letterhead: bool
    position: int
    fields: tuple[TemplateField, ...]
    blocks: tuple[dict, ...]


@dataclass
class FieldState:
    name: str
    label: str
    required: bool
    multiline: bool
    value: str
    source: str  # the source that filled it, "input", or ""
    where: str
    missing: bool = False
    savable: bool = False  # a typed value can be written back (SAVERS)
    choices: tuple[str, ...] = ()  # a fixed set of answers (a select, not free text)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "required": self.required,
            "multiline": self.multiline,
            "value": self.value,
            "source": self.source,
            "where": self.where,
            "missing": self.missing,
            "savable": self.savable,
            "choices": list(self.choices),
        }


@dataclass
class Resolution:
    template: DocTemplate
    fields: list[FieldState] = field(default_factory=list)

    @property
    def values(self) -> dict[str, str]:
        return {f.name: f.value for f in self.fields}

    @property
    def missing(self) -> list[FieldState]:
        return [f for f in self.fields if f.missing]


# ---------------------------------------------------------------------------
# Loading + validation
# ---------------------------------------------------------------------------


def _placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def _load(path: Path) -> DocTemplate:
    data = json.loads(path.read_text(encoding="utf-8"))
    fields = tuple(
        TemplateField(
            name=f["name"],
            label=f["label"],
            sources=tuple(f.get("sources", [])),
            required=bool(f.get("required", True)),
            multiline=bool(f.get("multiline", False)),
        )
        for f in data["fields"]
    )
    template = DocTemplate(
        key=data["key"],
        title=data["title"],
        description=data.get("description", ""),
        letterhead=bool(data.get("letterhead", False)),
        position=int(data.get("position", 100)),
        fields=fields,
        blocks=tuple(data["blocks"]),
    )
    _validate(template, path)
    return template


def _validate(template: DocTemplate, path: Path) -> None:
    """Fail loudly at load time rather than print a literal "{typo}"."""
    declared = {f.name for f in template.fields}
    if len(declared) != len(template.fields):
        raise ValueError(f"{path.name}: duplicate field names")
    for f in template.fields:
        for source in f.sources:
            if source not in SOURCES:
                raise ValueError(f"{path.name}: field {f.name!r} has unknown source {source!r}")
    for block in template.blocks:
        kind = block.get("type")
        if kind not in BLOCK_TYPES:
            raise ValueError(f"{path.name}: unknown block type {kind!r}")
        for key in ("text", "left", "right"):
            undeclared = _placeholders(block.get(key, "")) - declared
            if undeclared:
                raise ValueError(f"{path.name}: undeclared placeholders {sorted(undeclared)}")


@lru_cache(maxsize=1)
def _all_templates() -> dict[str, DocTemplate]:
    templates = {}
    for path in sorted(TEMPLATE_DIR.glob("*.json")):
        template = _load(path)
        if template.key in templates:
            raise ValueError(f"{path.name}: duplicate template key {template.key!r}")
        templates[template.key] = template
    return templates


def list_templates() -> list[DocTemplate]:
    """In each template's declared `position` (then key) -- the order the
    picker shows them, most-used first."""
    return sorted(_all_templates().values(), key=lambda t: (t.position, t.key))


def get_template(key: str) -> DocTemplate:
    try:
        return _all_templates()[key]
    except KeyError:
        raise UnknownTemplateError(f"No document template called {key!r}.") from None


# ---------------------------------------------------------------------------
# Sources: where a field's value can come from
# ---------------------------------------------------------------------------


# The date a document is signed, in India. TIME_ZONE is UTC (hearing dates
# are stored as UTC midnights), so timezone.localdate() is yesterday for the
# first 5.5 hours of every Indian day -- a vakalatnama signed at 2 am would
# carry the wrong date.
DOCUMENT_TIMEZONE = ZoneInfo("Asia/Kolkata")


def document_date():
    return timezone.localdate(timezone=DOCUMENT_TIMEZONE)


@dataclass
class Context:
    case: object
    profile: object
    contact: ClientContact | None
    client: object | None


def _court(ctx: Context) -> str:
    from core.services.parties import case_court_name

    return case_court_name(ctx.case)


def _user_side(ctx: Context) -> str:
    return {"petitioner": "Petitioner", "respondent": "Respondent"}.get(ctx.case.user_party_role, "")


def _party(which: str):
    def get(ctx: Context) -> str:
        from core.services.parties import case_parties

        return getattr(case_parties(ctx.case), which)

    return get


def _relation(ctx: Context) -> str:
    c = ctx.contact
    if c is None or not c.relation_type or not c.relation_name.strip():
        # Without S/o, D/o or W/o the phrase reads wrong -- ask for it.
        return ""
    return f"{c.get_relation_type_display()} {c.relation_name.strip()}"


def _contact_attr(attr):
    def get(ctx: Context) -> str:
        value = getattr(ctx.contact, attr, None) if ctx.contact else None
        return "" if value in (None, "") else str(value)

    return get


def _attr(obj_name: str, attr: str):
    def get(ctx: Context) -> str:
        obj = getattr(ctx, obj_name)
        value = getattr(obj, attr, None) if obj is not None else None
        return "" if value in (None, "") else str(value)

    return get


SOURCES = {
    "today": lambda ctx: document_date().strftime("%d %B %Y"),
    "case.title": _attr("case", "title"),
    "case.case_number": _attr("case", "case_number"),
    "case.cnr_number": _attr("case", "cnr_number"),
    "case.client_name": _attr("case", "client_name"),
    "case.opposing_party": _attr("case", "opposing_party"),
    # The record's parties, else the "X vs Y" title (core/services/parties.py).
    "case.petitioner_name": _party("petitioner"),
    "case.respondent_name": _party("respondent"),
    "case.court": _court,
    "case.user_side": _user_side,
    "case.our_party": _party("ours"),
    "profile.advocate_name": _attr("profile", "advocate_name"),
    "profile.letterhead_name": _attr("profile", "letterhead_name"),
    "profile.address": _attr("profile", "address"),
    "profile.bar_registration_number": _attr("profile", "bar_registration_number"),
    "profile.phone": _attr("profile", "phone"),
    "profile.contact_email": _attr("profile", "contact_email"),
    "contact.name": _contact_attr("name"),
    "contact.relation": _relation,
    "contact.age": _contact_attr("age"),
    "contact.address": _contact_attr("address"),
    "contact.email": _contact_attr("email"),
    "contact.phone": _contact_attr("phone"),
    "client.name": _attr("client", "name"),
    "client.address": _attr("client", "address"),
}


# ---------------------------------------------------------------------------
# Save for next time: where a typed answer can be written back
# ---------------------------------------------------------------------------

USER_SIDE_CHOICES = ("Petitioner", "Respondent")
_PROFILE_FIELDS = ("advocate_name", "letterhead_name", "address", "bar_registration_number", "phone", "contact_email")
_RELATION_TYPES = ("s/o", "d/o", "w/o", "c/o")


class SaveBackError(DocTemplateError):
    pass


def _save_profile(attr):
    def save(ctx: Context, value: str) -> None:
        setattr(ctx.profile, attr, value)
        ctx.profile.save(update_fields=[attr, "updated_at"])
        if attr in ("advocate_name", "letterhead_name"):
            # Waiting client-email drafts are signed with these; same as a
            # change made in Settings (views/advocate_profile.py).
            from core.services.client_updates.send import resign_open_drafts

            resign_open_drafts(ctx.profile.owner)

    return save


def _save_contact(attr):
    def save(ctx: Context, value: str) -> None:
        if ctx.contact is None:
            raise SaveBackError("There's no client contact on this case to save it to.")
        if attr == "age":
            if not value.isdigit() or not 0 < int(value) < 150:
                raise SaveBackError("Age must be a whole number to be saved.")
            value = int(value)
        setattr(ctx.contact, attr, value)
        ctx.contact.save(update_fields=[attr])

    return save


def _save_relation(ctx: Context, value: str) -> None:
    """ "S/o Venkat Rao" -> relation_type "s/o", relation_name "Venkat Rao"."""
    if ctx.contact is None:
        raise SaveBackError("There's no client contact on this case to save it to.")
    head, _, rest = value.strip().partition(" ")
    relation_type = head.lower().replace(".", "")
    if relation_type not in _RELATION_TYPES or not rest.strip():
        raise SaveBackError('Write the relation as "S/o Name", "D/o Name", "W/o Name" or "C/o Name" to save it.')
    ctx.contact.relation_type = relation_type
    ctx.contact.relation_name = rest.strip()
    ctx.contact.save(update_fields=["relation_type", "relation_name"])


def _save_user_side(ctx: Context, value: str) -> None:
    role = value.strip().lower()
    if role not in ("petitioner", "respondent"):
        raise SaveBackError("Your client's side must be Petitioner or Respondent.")
    ctx.case.user_party_role = role
    ctx.case.save(update_fields=["user_party_role"])


def _save_case(attr):
    def save(ctx: Context, value: str) -> None:
        setattr(ctx.case, attr, value)
        ctx.case.save(update_fields=[attr])

    return save


# First source of a field -> how to store a typed value there. A field
# whose first source isn't here (the date, the place, a letter's body, the
# court) has no home on the record and is only ever typed per document.
SAVERS = {
    **{f"profile.{attr}": _save_profile(attr) for attr in _PROFILE_FIELDS},
    "contact.name": _save_contact("name"),
    "contact.age": _save_contact("age"),
    "contact.address": _save_contact("address"),
    "contact.email": _save_contact("email"),
    "contact.phone": _save_contact("phone"),
    "contact.relation": _save_relation,
    "case.user_side": _save_user_side,
    "case.petitioner_name": _save_case("petitioner_name"),
    "case.respondent_name": _save_case("respondent_name"),
}


def _where(f: TemplateField) -> str:
    """Where the advocate can record this permanently, or "" when it has no
    home in the data and is always typed at generation time."""
    first = f.sources[0] if f.sources else ""
    if first.startswith("profile."):
        return "your profile in Settings"
    if first.startswith("contact."):
        return "the client contact on this case"
    if first == "case.court":
        return "court tracking for this case"
    if first in ("case.user_side", "case.our_party"):
        return "your client's side in the case details"
    if first.startswith("case."):
        return "the case details"
    if first.startswith("client."):
        return "the client record"
    return ""


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def pick_contact(case, contact_id: int | None) -> ClientContact | None:
    """The executant/recipient: the one asked for (must be on this case),
    else the case's primary contact, else its billing contact, else any."""
    contacts = ClientContact.objects.filter(case=case)
    if contact_id is not None:
        contact = contacts.filter(id=contact_id).first()
        if contact is None:
            raise InvalidContactError("That contact isn't on this case.")
        return contact
    return (
        contacts.filter(role="primary").order_by("id").first()
        or contacts.filter(is_billing_contact=True).first()
        or contacts.order_by("id").first()
    )


def resolve(template: DocTemplate, *, case, profile, contact=None, inputs: dict | None = None) -> Resolution:
    inputs = inputs or {}
    ctx = Context(case=case, profile=profile, contact=contact, client=case.client)
    resolution = Resolution(template=template)
    for f in template.fields:
        value, source = "", ""
        for name in f.sources:
            candidate = (SOURCES[name](ctx) or "").strip()
            if candidate:
                value, source = candidate, name
                break
        if not value:
            typed = str(inputs.get(f.name, "") or "").strip()[:MAX_INPUT_LENGTH]
            if typed and f.sources and f.sources[0] == "case.user_side":
                # A select in the dialog; anything else is not an answer.
                typed = next((c for c in USER_SIDE_CHOICES if c.lower() == typed.lower()), "")
            if typed:
                value, source = typed, "input"
        first = f.sources[0] if f.sources else ""
        resolution.fields.append(
            FieldState(
                name=f.name,
                label=f.label,
                required=f.required,
                multiline=f.multiline,
                value=value,
                source=source,
                where=_where(f),
                missing=f.required and not value,
                # A contact field has nowhere to go without a contact.
                savable=first in SAVERS and (contact is not None or not first.startswith("contact.")),
                choices=USER_SIDE_CHOICES if first == "case.user_side" else (),
            )
        )
    return resolution


def save_back(template: DocTemplate, resolution: Resolution, ctx: Context, names) -> list[str]:
    """Write the TYPED values of the fields in `names` back to their home.
    Values that came from the record already live there and are skipped.
    Returns the labels saved. Raises SaveBackError when a value can't be
    stored; the caller runs this in a transaction, before rendering."""
    by_name = {f.name: f for f in template.fields}
    states = {state.name: state for state in resolution.fields}
    saved = []
    for name in dict.fromkeys(names or []):
        field_def, state = by_name.get(name), states.get(name)
        if field_def is None or state is None or state.source != "input" or not state.savable:
            continue
        SAVERS[field_def.sources[0]](ctx, state.value)
        saved.append(state.label)
    return saved


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _merge_lines(text: str, values: dict[str, str]) -> list[str]:
    """Merge line by line, dropping a line only when it had placeholders and
    they all came out empty (an optional phone/email line) -- lines that are
    blank in the template itself are kept, they're deliberate spacing."""
    lines = []
    for line in text.split("\n"):
        merged = line.format_map(values)
        if _placeholders(line) and not merged.strip():
            continue
        lines.append(merged)
    return lines


def merged_text(template: DocTemplate, values: dict[str, str]) -> str:
    """Plain-text rendering, stored as the Document's extracted_text."""
    parts = []
    for block in template.blocks:
        if block["type"] == "spacer":
            parts.append("")
            continue
        if block["type"] == "signature":
            parts.append("\n".join(_merge_lines(block.get("left", ""), values)))
            parts.append("\n".join(_merge_lines(block.get("right", ""), values)))
            continue
        text = "\n".join(_merge_lines(block.get("text", ""), values)).replace("\t", " ")
        parts.append(text.upper() if block["type"] == "title" else text)
    return "\n".join(parts).strip() + "\n"


def render_pdf(template: DocTemplate, values: dict[str, str], profile) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(20, 18, 20)
    pdf.add_page()
    if template.letterhead:
        draw_letterhead(pdf, profile)

    width = pdf.w - pdf.l_margin - pdf.r_margin
    for block in template.blocks:
        kind = block["type"]
        if kind == "spacer":
            pdf.ln(float(block.get("height", 4)))
            continue
        if kind == "signature":
            _signature(pdf, block, values, width)
            continue

        lines = _merge_lines(block.get("text", ""), values)
        if kind == "title":
            pdf.set_font("Helvetica", "BU", 14)
            for line in lines:
                pdf.cell(0, 8, pdf_safe(line.upper()), align="C", new_x="LMARGIN", new_y="NEXT")
        elif kind == "center":
            pdf.set_font("Helvetica", "B", 11)
            for line in lines:
                pdf.multi_cell(0, 6, pdf_safe(line.upper()), align="C", new_x="LMARGIN", new_y="NEXT")
        elif kind == "heading":
            pdf.set_font("Helvetica", "B", 11)
            for line in lines:
                pdf.multi_cell(0, 6, pdf_safe(line), new_x="LMARGIN", new_y="NEXT")
        elif kind == "paragraph":
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 6, pdf_safe("\n".join(lines)), align="J", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
        elif kind == "text":
            pdf.set_font("Helvetica", "", 11)
            for line in lines:
                pdf.multi_cell(0, 6, pdf_safe(line), new_x="LMARGIN", new_y="NEXT")
        elif kind == "right":
            pdf.set_font("Helvetica", "", 11)
            for line in lines:
                pdf.multi_cell(0, 6, pdf_safe(line), align="R", new_x="LMARGIN", new_y="NEXT")
        elif kind == "parties":
            _parties(pdf, lines, width)

    return bytes(pdf.output())


def _parties(pdf, lines: list[str], width: float) -> None:
    """"Name\t... Petitioner(s)": the name wraps on the left, the party
    label sits right-aligned under it; AND is centred."""
    for line in lines:
        if line.strip().upper() in ("AND", "VS", "VS.", "VERSUS"):
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 7, pdf_safe(line.strip().upper()), align="C", new_x="LMARGIN", new_y="NEXT")
            continue
        if "\t" in line:
            name, label = line.split("\t", 1)
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(width, 6, pdf_safe(name), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "I", 11)
            pdf.cell(0, 6, pdf_safe(label), align="R", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 6, pdf_safe(line), new_x="LMARGIN", new_y="NEXT")


def _signature(pdf, block: dict, values: dict[str, str], width: float) -> None:
    """Two signature columns side by side."""
    pdf.set_font("Helvetica", "", 11)
    half = width / 2
    top = pdf.get_y()
    pdf.multi_cell(half, 6, pdf_safe("\n".join(_merge_lines(block.get("left", ""), values))))
    left_bottom = pdf.get_y()
    pdf.set_xy(pdf.l_margin + half, top)
    pdf.multi_cell(half, 6, pdf_safe("\n".join(_merge_lines(block.get("right", ""), values))), align="R")
    pdf.set_y(max(left_bottom, pdf.get_y()))


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def generate_document(
    case,
    template_key: str,
    *,
    profile,
    contact_id: int | None = None,
    inputs: dict | None = None,
    save: list[str] | None = None,
) -> Document:
    """Merge, render, and save the PDF as a Document on `case`.

    `save`: field names whose TYPED values should also be written back to
    the case, contact or profile ("Save for next time").

    Raises UnknownTemplateError, InvalidContactError, MissingFieldsError
    (carrying the list of what's missing) or SaveBackError -- in which case
    nothing is saved.
    """
    from django.db import transaction

    template = get_template(template_key)
    contact = pick_contact(case, contact_id)
    resolution = resolve(template, case=case, profile=profile, contact=contact, inputs=inputs)
    if resolution.missing:
        raise MissingFieldsError([f.as_dict() for f in resolution.missing])
    if save:
        with transaction.atomic():
            save_back(template, resolution, Context(case=case, profile=profile, contact=contact, client=case.client), save)

    values = resolution.values
    pdf_bytes = render_pdf(template, values, profile)

    stamp = timezone.localtime(timezone=DOCUMENT_TIMEZONE).strftime("%Y%m%d-%H%M%S")
    filename = f"{slugify(template.title) or template.key}-{slugify(case.case_number) or case.id}-{stamp}.pdf"
    saved = default_storage.save(f"generated/{case.owner_id}/{filename}", ContentFile(pdf_bytes))
    document = Document.objects.create(
        owner=case.owner,
        case=case,
        filename=filename,
        file_path=saved,
        file_type="pdf",
        file_size=len(pdf_bytes),
        document_type="generated",
        document_date=document_date(),
        # Nothing to extract or OCR: the text is ours. Not embedded -- a
        # template merge adds nothing Case Bot needs to search, and prod
        # has no embedding provider configured anyway.
        processing_status="completed",
        extracted_text=merged_text(template, values),
        chunk_count=0,
        content_hash=hashlib.sha256(pdf_bytes).hexdigest(),
    )
    logger.info("Generated %s for case %s as document %s.", template.key, case.id, document.id)
    return document
