"""The Order Overview prompt and its output contract.

Kept in its own module so the exact wording is reviewable and diffable
without reading the orchestration around it -- prompt changes are
behaviour changes here, since the JSON they produce is persisted.
"""

from __future__ import annotations

# Orders run long (a judgment can be dozens of pages) and the whole
# document is never needed to answer "what happened and what must each
# side do" -- the operative portion is at the end, and the head carries
# the cause title. Truncating bounds the per-order cost.
MAX_ORDER_CHARS = 12000
# When truncating, keep the head (cause title, parties) AND the tail (the
# operative directions), which is where the answer actually lives.
HEAD_CHARS = 4000

SYSTEM_PROMPT = (
    "You are a legal assistant summarising ONE court order from an Indian "
    "court for the advocate on record. Output ONLY a valid JSON object "
    "matching the schema you are given -- no prose, no markdown, no code "
    "fences.\n\n"
    "Use ONLY facts stated in the order text. Never invent or infer dates, "
    "party names, or directions. If the order does not state something, use "
    "null or an empty list. Accuracy matters more than completeness: an "
    "empty field is correct when the order is silent, a guessed one is not."
)

RESPONSE_SCHEMA = """{
  "what_happened": "1-3 sentences, plain English, on what the court actually did at this hearing",
  "petitioner_directions": ["each direction the order addresses to the petitioner side"],
  "respondent_directions": ["each direction the order addresses to the respondent side"],
  "next_date": "YYYY-MM-DD, or null if the order states no next date",
  "next_date_purpose": "what the next date is for, or null",
  "is_routine_adjournment": true
}"""

RULES = """Rules:
- Use ONLY the order text above. Do not use outside knowledge of the case.
- Write for an advocate: name what must be done, by whom, and by when.
- If a direction's addressee is unclear, assign it to the side the order
  actually names. Do not guess, and do not put the same direction on both
  sides unless the order genuinely directs both.
- Use an empty list for a side the order gives no directions to.
- "next_date" must be a date printed in the order. Never compute, infer,
  or carry forward a date from anywhere else. Use null if none is stated.
- "is_routine_adjournment" is true only if the order does nothing but
  adjourn/relist the matter."""


def truncate_order_text(text: str) -> str:
    """Head + tail of a long order, with the elision marked.

    The tail is what carries the operative directions, so a naive
    head-only truncation would reliably cut off the part that matters.
    """
    text = (text or "").strip()
    if len(text) <= MAX_ORDER_CHARS:
        return text

    tail_chars = MAX_ORDER_CHARS - HEAD_CHARS
    return (
        text[:HEAD_CHARS]
        + "\n\n[... middle of the order omitted for length ...]\n\n"
        + text[-tail_chars:]
    )


def build_messages(order, order_text: str) -> list[dict]:
    """Chat messages for a first-attempt summarisation."""
    case = order.case
    header_lines = [
        f"CASE: {case.title or case.case_number}",
        f"CASE NUMBER: {case.case_number}",
    ]
    if case.cnr_number:
        header_lines.append(f"CNR: {case.cnr_number}")
    if order.order_date:
        header_lines.append(f"ORDER DATE: {order.order_date.isoformat()}")
    if order.judge:
        header_lines.append(f"JUDGE: {order.judge}")
    if order.description:
        header_lines.append(f"PORTAL DESCRIPTION: {order.description}")

    user_content = (
        "\n".join(header_lines)
        + "\n\nORDER TEXT:\n\"\"\"\n"
        + truncate_order_text(order_text)
        + "\n\"\"\"\n\nReturn a JSON object with exactly these keys:\n"
        + RESPONSE_SCHEMA
        + "\n\n"
        + RULES
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_retry_messages(order, order_text: str, bad_response: str) -> list[dict]:
    """Second and final attempt, after the first reply failed to parse.

    Feeds the bad reply back rather than just re-asking -- a model that
    wrapped its JSON in prose or a code fence corrects that reliably when
    shown what it did.
    """
    messages = build_messages(order, order_text)
    messages.append({"role": "assistant", "content": (bad_response or "")[:2000]})
    messages.append(
        {
            "role": "user",
            "content": (
                "That response was not a valid JSON object matching the schema. "
                "Reply again with ONLY the JSON object -- no explanation, no "
                "markdown, no code fences, starting with { and ending with }."
            ),
        }
    )
    return messages
