"""Order Overview: a one-off, cached AI summary of a single court order.

Three rules shape this package:

1. **Run once, at ingest, cache forever.** A summary is generated when the
   order's document finishes processing and is then read from the row on
   every page view. Nothing here is ever called from a serializer or a
   GET handler.

2. **Never call the LLM without earning it.** `routing.py` classifies
   every order BEFORE any model call -- unreadable (scanned) and
   routine-adjournment orders are resolved by template at zero cost.
   This is a free product; each avoided call is real money.

3. **Party-aware at render time, not at generation time.** The LLM is
   asked for petitioner/respondent directions as they appear in the
   order. Which of those is "your side" is applied by the serializer from
   Case.user_party_role -- so a case whose role is corrected later
   re-renders correctly with no re-generation.
"""

from .routing import (
    ROUTE_LLM,
    ROUTE_ROUTINE,
    ROUTE_SHORT,
    ROUTE_UNREADABLE,
    classify_order_text,
)
from .service import (
    OrderSummaryError,
    summarize_court_order,
    summarize_order_text,
)

__all__ = [
    "ROUTE_LLM",
    "ROUTE_ROUTINE",
    "ROUTE_SHORT",
    "ROUTE_UNREADABLE",
    "OrderSummaryError",
    "classify_order_text",
    "summarize_court_order",
    "summarize_order_text",
]
