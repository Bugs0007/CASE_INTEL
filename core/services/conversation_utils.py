"""
Helpers for conversation titles, transcript export, and source cleanup.
"""

from __future__ import annotations

import re
from io import BytesIO

from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

TITLE_MAX_LENGTH = 50
PREVIEW_MAX_LENGTH = 60
WINDOWS_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
SOURCES_SECTION_RE = re.compile(
    r"(?:\r?\n){2,}(?:\*\*|__)?sources:(?:\*\*|__)?[\s\S]*$",
    re.IGNORECASE,
)
MARKDOWN_DECORATION_RE = re.compile(r"(^|\s)([#>`*_]{1,3})(?=\S)|(?<=\S)([#>`*_]{1,3})(?=\s|$)")


def normalize_whitespace(value: str | None) -> str:
    return " ".join((value or "").split())


def truncate_on_word_boundary(value: str | None, max_length: int) -> str:
    text = normalize_whitespace(value)
    if not text:
        return ""
    if len(text) <= max_length:
        return text

    candidate = text[: max_length + 1]
    head = candidate[:max_length].rstrip(" ,;:-")
    if " " in head:
        trimmed = head.rsplit(" ", 1)[0].rstrip(" ,;:-")
        if trimmed and len(trimmed) >= max(12, max_length // 2):
            return trimmed
    return head


def generate_conversation_title(first_user_message: str | None) -> str:
    return truncate_on_word_boundary(first_user_message, TITLE_MAX_LENGTH) or "New Conversation"


def generate_conversation_preview(first_user_message: str | None) -> str:
    return truncate_on_word_boundary(first_user_message, PREVIEW_MAX_LENGTH)


def strip_embedded_sources_section(content: str | None) -> str:
    if not content:
        return ""
    return SOURCES_SECTION_RE.sub("", content).strip()


def markdown_to_plain_text(content: str | None) -> str:
    if not content:
        return ""
    text = strip_embedded_sources_section(content)
    text = text.replace("\r\n", "\n")
    text = MARKDOWN_DECORATION_RE.sub(lambda match: match.group(1) or "", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def sanitize_filename_part(value: str | None, fallback: str) -> str:
    cleaned = WINDOWS_FILENAME_RE.sub("", normalize_whitespace(value))
    cleaned = cleaned.strip(" .")
    if not cleaned:
        cleaned = fallback
    return cleaned.replace(" ", "_")


def build_export_filename(conversation, extension: str) -> str:
    case_name = sanitize_filename_part(
        getattr(conversation.case, "title", None),
        "case",
    )
    title = sanitize_filename_part(conversation.title, f"conversation_{conversation.id}")
    stamp = timezone.localdate().isoformat()
    return f"{case_name}_{title}_{stamp}.{extension}"


def get_display_title(conversation) -> str:
    title = normalize_whitespace(getattr(conversation, "title", None))
    if title:
        return title
    first_user_message = getattr(conversation, "first_user_message", None)
    if first_user_message is None and hasattr(conversation, "messages"):
        first_message = next(
            (message.content for message in conversation.messages.all() if message.role == "user"),
            "",
        )
        first_user_message = first_message
    return generate_conversation_title(first_user_message)


def get_conversation_preview(conversation) -> str:
    preview_source = getattr(conversation, "first_user_message", None)
    if preview_source is None and hasattr(conversation, "messages"):
        preview_source = next(
            (message.content for message in conversation.messages.all() if message.role == "user"),
            "",
        )
    return generate_conversation_preview(preview_source)


def get_citation_source_names(message) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for citation in message.citations.all():
        name = None
        if citation.document_id and citation.document:
            name = citation.document.filename
        elif citation.chunk_id and citation.chunk and citation.chunk.document:
            name = citation.chunk.document.filename
        elif citation.email_id and citation.email:
            name = citation.email.subject or f"Email {citation.email_id}"
        if not name:
            continue
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def _build_transcript_entries(conversation, markdown: bool) -> list[dict]:
    entries: list[dict] = []
    for message in conversation.messages.all():
        entries.append(
            {
                "speaker": "You" if message.role == "user" else "Assistant",
                "content": (
                    strip_embedded_sources_section(message.content)
                    if markdown
                    else markdown_to_plain_text(message.content)
                ),
                "sources": get_citation_source_names(message)
                if message.role == "assistant"
                else [],
            }
        )
    return entries


def build_text_transcript(conversation) -> str:
    exported_at = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S %Z")
    case_name = getattr(conversation.case, "title", "No Case")
    lines = [
        f"Case: {case_name}",
        f"Conversation: {get_display_title(conversation)}",
        f"Exported: {exported_at}",
        "",
    ]
    for entry in _build_transcript_entries(conversation, markdown=False):
        lines.append(f"{entry['speaker']}:")
        lines.append(entry["content"] or "(empty)")
        if entry["sources"]:
            lines.append("Sources:")
            lines.extend(f"- {source}" for source in entry["sources"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_markdown_transcript(conversation) -> str:
    exported_at = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S %Z")
    case_name = getattr(conversation.case, "title", "No Case")
    lines = [
        f"# {case_name}",
        "",
        f"**Conversation:** {get_display_title(conversation)}",
        f"**Exported:** {exported_at}",
        "",
    ]
    for entry in _build_transcript_entries(conversation, markdown=True):
        lines.append(f"## {entry['speaker']}")
        lines.append("")
        lines.append(entry["content"] or "(empty)")
        lines.append("")
        if entry["sources"]:
            lines.append("**Sources:**")
            lines.extend(f"- {source}" for source in entry["sources"])
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    if not text:
        return [""]
    wrapped: list[str] = []
    for raw_line in text.splitlines() or [""]:
        words = raw_line.split()
        if not words:
            wrapped.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                wrapped.append(current)
                current = word
        wrapped.append(current)
    return wrapped


def build_pdf_transcript(conversation) -> bytes:
    page_width, page_height = 1654, 2339
    margin_x, margin_y = 110, 120
    content_width = page_width - (margin_x * 2)
    title_font = _load_font(34, bold=True)
    body_font = _load_font(24)
    label_font = _load_font(24, bold=True)
    meta_font = _load_font(20)

    pages: list[Image.Image] = []
    image = Image.new("RGB", (page_width, page_height), "white")
    draw = ImageDraw.Draw(image)
    y = margin_y

    def new_page() -> None:
        nonlocal image, draw, y
        pages.append(image)
        image = Image.new("RGB", (page_width, page_height), "white")
        draw = ImageDraw.Draw(image)
        y = margin_y

    def ensure_space(height: int) -> None:
        nonlocal y
        if y + height > page_height - margin_y:
            new_page()

    def draw_block(text: str, font, fill: str = "#111827", gap: int = 10) -> None:
        nonlocal y
        for line in _wrap_text(draw, text, font, content_width):
            line_height = draw.textbbox((0, 0), line or "Ag", font=font)[3] + 10
            ensure_space(line_height)
            draw.text((margin_x, y), line, font=font, fill=fill)
            y += line_height
        y += gap

    case_name = getattr(conversation.case, "title", "No Case")
    exported_at = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S %Z")

    draw_block(case_name, title_font, gap=18)
    draw_block(f"Conversation: {get_display_title(conversation)}", label_font, gap=6)
    draw_block(f"Exported: {exported_at}", meta_font, fill="#4b5563", gap=24)

    for entry in _build_transcript_entries(conversation, markdown=False):
        draw_block(entry["speaker"], label_font, fill="#1d4ed8" if entry["speaker"] == "You" else "#111827", gap=4)
        draw_block(entry["content"] or "(empty)", body_font, gap=8)
        if entry["sources"]:
            draw_block("Sources:", meta_font, gap=2)
            for source in entry["sources"]:
                draw_block(f"- {source}", meta_font, fill="#4b5563", gap=2)
        y += 12

    pages.append(image)
    rgb_pages = [page.convert("RGB") for page in pages]
    buffer = BytesIO()
    rgb_pages[0].save(buffer, format="PDF", save_all=True, append_images=rgb_pages[1:])
    return buffer.getvalue()
