"""The MCP tool registry: every tool reviewed, annotated, safely shaped.

Like TestEndpointTenancyCoverage for REST: adding a tool without listing it
here (and so without a tenancy test) fails the build.
"""

import ast
import asyncio
import re
from pathlib import Path

import pytest

import mcp_server.django_setup  # noqa: F401
import mcp_server.tools  # noqa: F401
from mcp_server.registry import (
    KIND_PROPOSAL_ACTION,
    KIND_PROPOSE,
    KIND_PUBLIC_LAW,
    KIND_READ,
    REGISTRY,
    SCOPE_READ,
    SCOPE_WRITE,
)

MCP_DIR = Path(__file__).resolve().parents[2] / "mcp_server"

# Reviewed 2026-11-25 (Phase 1). Each has a cross-tenant test in test_mcp_tools.py.
_READ_TOOLS = {
    "get_schedule",
    "list_cases",
    "get_case",
    "get_last_order",
    "list_orders",
    "get_hearing_prep",
    "list_tasks",
    "search_case_documents",
    "list_client_drafts",
    "list_unpaid_fees",
    "get_data_freshness",
}
# Phase 2: propose-then-confirm. Each propose tool writes only McpProposal.
_PROPOSE_TOOLS = {
    "propose_task",
    "propose_case_note",
    "propose_case_event",
    "propose_task_update",
    "propose_client_update_draft",
}
_PROPOSAL_ACTION_TOOLS = {"confirm_proposal", "cancel_proposal"}
_PUBLIC_LAW_TOOLS: set = set()  # Phase 4, not built

_KIND_LISTS = {
    KIND_READ: _READ_TOOLS,
    KIND_PROPOSE: _PROPOSE_TOOLS,
    KIND_PROPOSAL_ACTION: _PROPOSAL_ACTION_TOOLS,
    KIND_PUBLIC_LAW: _PUBLIC_LAW_TOOLS,
}

FORBIDDEN_INPUTS = {
    "owner", "owner_id", "owner_ids", "user", "user_id", "org", "org_id", "organization", "organization_id",
    "url", "uri", "link", "path", "file", "file_path", "filename", "email", "emails", "recipient",
    "recipients", "to", "cc", "token",
}
# Actions no tool may perform (docs/MCP_PLAN.md section 5).
FORBIDDEN_NAME = re.compile(
    r"send|email|whatsapp|invoice|mark_paid|pay|delete|remove|refresh|import|advocate_search|fetch|sync|"
    r"track|password|settings|party_role"
)


def _listed_tools():
    from mcp_server.app import build_server

    return asyncio.run(build_server().list_tools())


def test_every_tool_is_in_a_reviewed_list_of_its_kind():
    for name, spec in REGISTRY.items():
        assert name in _KIND_LISTS[spec.kind], f"{name} ({spec.kind}) is not in its reviewed list"


def test_reviewed_lists_have_no_stale_entries():
    listed = set().union(*_KIND_LISTS.values())
    assert listed - set(REGISTRY) == set()


def test_scopes_match_kind():
    for spec in REGISTRY.values():
        expected = SCOPE_READ if spec.kind in (KIND_READ,) else SCOPE_WRITE
        if spec.kind == KIND_PUBLIC_LAW:
            expected = "publiclaw:read"
        assert spec.scope == expected, spec.name


def test_every_tool_has_all_four_annotations_on_the_wire():
    tools = _listed_tools()
    assert {t.name for t in tools} == set(REGISTRY)
    for t in tools:
        a = t.annotations
        assert a is not None, t.name
        for hint in ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"):
            assert getattr(a, hint) is not None, f"{t.name} lacks {hint}"
        assert a.destructiveHint is False and a.openWorldHint is False, t.name
        if REGISTRY[t.name].kind in (KIND_READ, KIND_PUBLIC_LAW):
            assert a.readOnlyHint is True and a.idempotentHint is True, t.name
        else:
            assert a.readOnlyHint is False, t.name


def test_no_tool_takes_an_owner_user_org_url_or_recipient_input():
    for t in _listed_tools():
        names = set((t.inputSchema.get("properties") or {}).keys())
        assert not names & FORBIDDEN_INPUTS, f"{t.name} takes {names & FORBIDDEN_INPUTS}"


def test_no_forbidden_action_tool_exists():
    offenders = [name for name in REGISTRY if FORBIDDEN_NAME.search(name)]
    assert offenders == []


def test_descriptions_mark_court_text_untrusted():
    for t in _listed_tools():
        assert "untrusted data" in (t.description or ""), t.name


def test_tool_code_gets_rows_only_through_scoped():
    """docs/MCP_PLAN.md section 4: `.objects.` never appears in tool code."""
    for path in (MCP_DIR / "tools").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert ".objects." not in text, f"{path.name} queries a model directly; use scoped()"
        assert "_default_manager" not in text, path.name


def test_tool_modules_do_not_postpone_annotations():
    """The SDK builds input schemas from real type objects."""
    for path in (MCP_DIR / "tools").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                assert not any(a.name == "annotations" for a in node.names), path.name


@pytest.mark.parametrize("name", sorted(_READ_TOOLS))
def test_read_tool_is_registered(name):
    assert REGISTRY[name].kind == KIND_READ
