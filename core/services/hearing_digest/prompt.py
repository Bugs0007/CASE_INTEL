"""The case briefing prompt.

Kept in its own module, like order_summary/prompt.py, so the wording is
reviewable on its own -- the output is persisted, so a prompt change is a
behaviour change.
"""

from __future__ import annotations

import json

SYSTEM_PROMPT = (
    "You are a legal assistant writing a short briefing for an advocate "
    "preparing for the next hearing of a case in an Indian court.\n\n"
    "Write ONE paragraph of 3 to 6 sentences of plain prose -- no headings, "
    "lists, markdown or quotation marks -- on the current state of the "
    "matter: where it stands, what the court has done recently, what the "
    "orders have directed, and what the next hearing is for.\n\n"
    "Use ONLY the facts provided. Never invent or infer dates, names, "
    "directions or outcomes, and never say whether a direction has been "
    "complied with unless the facts say so. Refer to the parties only as "
    "'the petitioner' and 'the respondent' -- never 'you', 'your client' or "
    "'the other side'. If the facts are thin, write less rather than guess."
)


def build_messages(inputs: dict) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "CASE FACTS (JSON, oldest first):\n"
                + json.dumps(inputs, indent=2, ensure_ascii=False)
                + "\n\nWrite the briefing paragraph."
            ),
        },
    ]
