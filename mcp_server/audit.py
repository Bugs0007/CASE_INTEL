"""One ActivityLog row per tool call (docs/MCP_PLAN.md section 6, Audit log).

`description` is compact JSON: tool, client_id, token_id, safe args (ids,
dates, enums and short fields; never document text; a query only as its
length), result, rows, duration_ms, proposal_id. A failed audit write never
fails the call; it is logged at ERROR. A confirmed write saves its audit
row inside the write's own transaction (see tools/proposals.py).
"""

from __future__ import annotations

import json
import logging

from core.models import ActivityLog

logger = logging.getLogger("mcp_server.audit")

ACTIVITY_READ = "mcp_call"
ACTIVITY_WRITE = "mcp_write"

# Argument names whose values are never stored, only their length.
_TEXT_ARGS = {"query", "text", "title", "description", "body", "note"}


def safe_args(args: dict) -> dict:
    out = {}
    for key, value in (args or {}).items():
        if value is None:
            continue
        if key in _TEXT_ARGS:
            out[f"{key}_len"] = len(str(value))
        elif isinstance(value, (int, float, bool)):
            out[key] = value
        else:
            out[key] = str(value)[:40]
    return out


def describe(*, tool, ctx_client_id, token_id, args, result, rows=None, duration_ms=None, proposal_id=None):
    payload = {
        "tool": tool,
        "client_id": (ctx_client_id or "")[:200],
        "token_id": token_id,
        "args": safe_args(args),
        "result": result,
    }
    if rows is not None:
        payload["rows"] = rows
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if proposal_id is not None:
        payload["proposal_id"] = proposal_id
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def record(*, owner, activity_type, case_id=None, **fields) -> None:
    """Write the audit row; never raise."""
    try:
        ActivityLog.objects.create(
            owner=owner,
            case_id=case_id,
            activity_type=activity_type,
            description=describe(**fields),
        )
    except Exception:  # noqa: BLE001 -- an audit failure must not fail the call
        logger.error("MCP audit write failed for tool %s", fields.get("tool"), exc_info=True)
