"""Case Intel's remote MCP server (docs/MCP_PLAN.md).

A separate uvicorn process (`uvicorn mcp_server.app:app`) that serves the
Model Context Protocol over Streamable HTTP. It is an OAuth 2.1 resource
server only: tokens are issued by the Django app (django-oauth-toolkit) and
read here from the shared database.

Rules this package keeps (tests in core/tests/test_mcp_*.py enforce them):

  - every row comes through access.scoped(); no tool takes owner/user_id/
    org_id/url as input;
  - no court portal is ever called: nothing here imports bharat_courts,
    core.services.court_data, court_tracking, court_order_sync,
    causelists.service or advocate_search*, nor core.services.reranker;
  - court text leaves only as labelled, cleaned, capped `untrusted_text`;
  - read tools never write case data; writes are propose-then-confirm.
"""
