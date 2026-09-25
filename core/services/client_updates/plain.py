"""A lay reader's version of an order summary, for client emails.

The Order Overview is written for the advocate ("the proviso to Rule
3(a)(iii) be read to include..."), which is right on the case page and
wrong in an email to a client. This asks the LLM once per order to say the
same thing in plain English and stores it on the order (summary_plain);
client updates use it and fall back to the advocate's text whenever there
is none -- no LLM configured, a failed call, an unusable answer.

Only orders that went through the LLM summary get one: the templated
paths ("no directions", "unreadable") already have plain client wording
in compose.py. Uses get_llm_client() directly, like the order summary --
not the Case Bot graph.
"""

from __future__ import annotations

import json
import logging

from core.models import CourtOrder

logger = logging.getLogger(__name__)

MAX_PLAIN_CHARS = 700

SYSTEM_PROMPT = (
    "You rewrite a lawyer's summary of an Indian court order for the client, a "
    "person with no legal training. Output ONLY a JSON object: "
    '{"plain": "..."}. No markdown, no code fences.'
)

RULES = """Rules:
- 2 to 4 short sentences, plain everyday English.
- Say what the court decided or did and what it means for the client.
- No section, rule, article or G.O. numbers, no Latin, no legal jargon;
  say "the court", "the government", "the university" -- whoever it is.
- Use ONLY what the summary says. Add no facts, dates or advice, and do
  not promise an outcome.
- Do not address the client by name or sign off."""


def _prompt(order: CourtOrder) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "LAWYER'S SUMMARY OF THE ORDER:\n\"\"\"\n"
                + (order.summary_what_happened or "").strip()
                + "\n\"\"\"\n\n"
                + RULES
            ),
        },
    ]


def _parse(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    data = json.loads(text)
    plain = str(data.get("plain") or "").strip() if isinstance(data, dict) else ""
    if not plain or len(plain) > MAX_PLAIN_CHARS:
        raise ValueError("empty or overlong plain summary")
    return plain


def ensure_plain_summary(order: CourtOrder) -> str:
    """The order's plain-language summary, generating it once if missing.
    Returns "" (and stores nothing) when it can't be made -- callers then
    use summary_what_happened."""
    if order.summary_plain:
        return order.summary_plain
    if order.summary_status != CourtOrder.SUMMARY_SUMMARIZED or not (order.summary_what_happened or "").strip():
        return ""
    try:
        from core.services.ai_service_factory import get_llm_client

        plain = _parse(get_llm_client().generate_with_json(_prompt(order), temperature=0))
    except Exception:  # noqa: BLE001 -- no LLM, a failed call, a bad answer: fall back
        logger.warning("Order %s: no plain-language summary; client emails use the advocate's text.", order.id, exc_info=True)
        return ""
    order.summary_plain = plain
    order.save(update_fields=["summary_plain"])
    return plain
