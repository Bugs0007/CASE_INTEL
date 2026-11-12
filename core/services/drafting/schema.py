"""The structured body of an assistant draft, and its validator.

A model only ever proposes this body. Owner, case, approval, destinations and
file writes are decided by server code and are not part of it. The frontend
mirror is frontend-next/types/draft.ts. Change both together.

validate_body() is the single gate: generation output, the repair attempt and
every user edit pass through it before a revision is stored.
"""
from typing import Any, Iterable

SCHEMA_VERSION = 1

SUBTYPES = ("status_memo", "personal_note")
BLOCK_TYPES = ("paragraph", "bullets", "table")

MAX_TITLE = 200
MAX_SECTIONS = 20
MAX_BLOCKS_PER_SECTION = 30
MAX_TEXT = 4000
MAX_ITEMS = 40
MAX_TABLE_ROWS = 40
MAX_TABLE_COLS = 6
MAX_CELL = 500
MAX_LIST = 30

_BODY_KEYS = {"schema_version", "title", "subtype", "sections", "verification_items", "warnings"}
_SECTION_KEYS = {"heading", "blocks"}
_BLOCK_KEYS = {
    "paragraph": {"type", "text", "evidence", "is_suggestion"},
    "bullets": {"type", "items", "evidence", "is_suggestion"},
    "table": {"type", "columns", "rows", "evidence", "is_suggestion"},
}


class DraftValidationError(ValueError):
    """The body is not storable. `errors` is a list of short, safe messages."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors[:5]))
        self.errors = errors


def _is_text(value: Any, limit: int, *, allow_empty: bool = False) -> bool:
    if not isinstance(value, str) or len(value) > limit:
        return False
    if not allow_empty and not value.strip():
        return False
    # Plain text only: a draft never carries markup.
    return "<" not in value or ">" not in value


def _text_list(value: Any, max_len: int, item_limit: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) <= max_len
        and all(_is_text(v, item_limit) for v in value)
    )


def validate_body(body: Any, *, allowed_evidence: Iterable[str]) -> dict:
    """Return the body unchanged if valid, else raise DraftValidationError.

    `allowed_evidence` is the set of evidence IDs the server collected for
    this draft (for example "hearing:18", "task:7", "doc:42:p3"). A block may
    cite only those; anything else is treated as invented and rejected.
    Unknown keys are rejected rather than dropped, so a model cannot smuggle
    fields past the schema.
    """
    allowed = set(allowed_evidence)
    errors: list[str] = []

    if not isinstance(body, dict):
        raise DraftValidationError(["body must be an object"])
    extra = set(body) - _BODY_KEYS
    if extra:
        errors.append(f"unknown fields: {sorted(extra)}")
    if body.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported schema_version")
    if not _is_text(body.get("title"), MAX_TITLE):
        errors.append("title is missing, too long or contains markup")
    if body.get("subtype") not in SUBTYPES:
        errors.append("unknown subtype")
    for key in ("verification_items", "warnings"):
        if not _text_list(body.get(key, []), MAX_LIST, MAX_CELL):
            errors.append(f"{key} must be a short list of plain text")

    sections = body.get("sections")
    if not isinstance(sections, list) or not 1 <= len(sections) <= MAX_SECTIONS:
        errors.append("sections must be a non-empty list")
        raise DraftValidationError(errors)

    for si, section in enumerate(sections):
        where = f"section {si + 1}"
        if not isinstance(section, dict) or set(section) - _SECTION_KEYS:
            errors.append(f"{where}: malformed")
            continue
        if not _is_text(section.get("heading"), MAX_TITLE):
            errors.append(f"{where}: heading is missing or invalid")
        blocks = section.get("blocks")
        if not isinstance(blocks, list) or len(blocks) > MAX_BLOCKS_PER_SECTION:
            errors.append(f"{where}: blocks must be a list")
            continue
        for bi, block in enumerate(blocks):
            at = f"{where} block {bi + 1}"
            kind = block.get("type") if isinstance(block, dict) else None
            if kind not in BLOCK_TYPES:
                errors.append(f"{at}: unknown block type")
                continue
            if set(block) - _BLOCK_KEYS[kind]:
                errors.append(f"{at}: unknown fields")
            if not isinstance(block.get("is_suggestion", False), bool):
                errors.append(f"{at}: is_suggestion must be true or false")
            evidence = block.get("evidence", [])
            if not isinstance(evidence, list) or not all(isinstance(e, str) for e in evidence):
                errors.append(f"{at}: evidence must be a list of IDs")
            elif set(evidence) - allowed:
                errors.append(f"{at}: cites evidence that was not collected")
            if kind == "paragraph" and not _is_text(block.get("text"), MAX_TEXT):
                errors.append(f"{at}: text is missing, too long or contains markup")
            if kind == "bullets" and not (
                block.get("items") and _text_list(block.get("items"), MAX_ITEMS, MAX_TEXT)
            ):
                errors.append(f"{at}: items must be a non-empty list of plain text")
            if kind == "table":
                columns, rows = block.get("columns"), block.get("rows")
                if not (columns and _text_list(columns, MAX_TABLE_COLS, MAX_CELL)):
                    errors.append(f"{at}: columns invalid")
                elif not (
                    isinstance(rows, list)
                    and len(rows) <= MAX_TABLE_ROWS
                    and all(
                        isinstance(r, list)
                        and len(r) == len(columns)
                        and all(_is_text(c, MAX_CELL, allow_empty=True) for c in r)
                        for r in rows
                    )
                ):
                    errors.append(f"{at}: rows must match the columns")

    if errors:
        raise DraftValidationError(errors)
    return body
