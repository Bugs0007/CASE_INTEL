"""The MCP process never calls a court portal (docs/MCP_PLAN.md section 6).

Two checks: (1) nothing in mcp_server/ imports a portal module, directly or
through what it imports -- checked in a fresh interpreter; (2) every tool
still works with the eCourts provider and bharat_courts patched to raise.
"""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.tests.mcp_support import (  # noqa: F401 -- fixtures
    READ_TOOL_ARGS,
    _mcp_settings,
    _stub_search_embeddings,
    call,
    ctx_for,
    make_tenant,
)

ROOT = Path(__file__).resolve().parents[2]
MCP_DIR = ROOT / "mcp_server"

FORBIDDEN_MODULES = (
    "bharat_courts",
    "core.services.court_data",
    "core.services.court_tracking",
    "core.services.court_order_sync",
    "core.services.causelists.service",
    "core.services.advocate_search",
    "core.services.advocate_search_v2",
    "core.services.advocate_import",
    "core.services.advocate_quick_search",
    "core.services.bulk_refresh",
)
# Never loaded by the MCP process at start (search loads no model either:
# search_backend builds VectorSearchService(use_reranker=False)).
HEAVY_MODULES = ("torch", "sentence_transformers", "transformers", "onnxruntime", "core.services.reranker")


def _imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_no_mcp_server_module_imports_a_portal_module():
    for path in MCP_DIR.rglob("*.py"):
        for name in _imports(path):
            assert not name.startswith(FORBIDDEN_MODULES), f"{path.relative_to(ROOT)} imports {name}"
            assert not name.startswith("core.services.reranker"), path.name


def test_loading_the_mcp_app_loads_no_portal_or_heavy_module():
    code = (
        "import json, sys\n"
        "import mcp_server.app\n"
        "print(json.dumps(sorted(m for m in sys.modules)))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=180,
        env={**os.environ, "DJANGO_SETTINGS_MODULE": "case_intel_project.settings"},
    )
    assert out.returncode == 0, out.stderr[-2000:]
    loaded = json.loads(out.stdout.strip().splitlines()[-1])
    bad = [m for m in loaded if m.startswith(FORBIDDEN_MODULES + HEAVY_MODULES)]
    assert bad == []


def test_search_backend_never_loads_the_reranker():
    from mcp_server.tools import search_backend

    search_backend._service = None
    service = search_backend._get_service()
    assert service._use_reranker is False


@pytest.mark.django_db
def test_every_read_tool_works_with_the_portal_patched_to_raise(monkeypatch):
    import bharat_courts

    from core.services.court_data import ecourts_provider

    def explode(*args, **kwargs):
        raise AssertionError("an MCP tool reached the court portal")

    monkeypatch.setattr(ecourts_provider.EcourtsProvider, "__init__", explode)
    for name in dir(bharat_courts):
        if not name.startswith("_") and callable(getattr(bharat_courts, name)):
            monkeypatch.setattr(bharat_courts, name, explode)

    tenant = make_tenant("guard_a", "Ramesh")
    ctx = ctx_for(tenant.user)
    for name, args in READ_TOOL_ARGS.items():
        result = call(ctx, name, **args(tenant))
        assert not result.isError, (name, result.content[0].text)
