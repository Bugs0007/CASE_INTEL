"""Shared shape for the Order Overview payload.

Both CourtOrderSerializer (case page) and HearingSerializer (calendar
entry) return the summary, and they must return the SAME shape --
otherwise the frontend needs two renderers for one concept and they drift.
"""

from __future__ import annotations


def build_order_summary(order) -> dict:
    """Render `order`'s stored summary from its case's point of view.

    The party-aware split happens HERE, at render time, from
    Case.user_party_role -- never at generation time. An advocate who
    corrects their party role later immediately sees the right framing
    with no re-generation and no second LLM call.

    When the role is "unknown", your_side/other_side are None and the
    caller must show both sides neutrally. Guessing would be worse than
    showing both: acting on the opposing side's directions is the actual
    harm this feature could cause.
    """
    role = order.case.user_party_role
    petitioner = order.summary_petitioner_directions or []
    respondent = order.summary_respondent_directions or []

    if role == "petitioner":
        your_side, other_side = petitioner, respondent
        your_label, other_label = "You (Petitioner)", "Respondent"
    elif role == "respondent":
        your_side, other_side = respondent, petitioner
        your_label, other_label = "You (Respondent)", "Petitioner"
    else:
        your_side = other_side = None
        your_label = other_label = None

    return {
        "status": order.summary_status,
        "status_display": order.get_summary_status_display(),
        "route": order.summary_route,
        "what_happened": order.summary_what_happened,
        "petitioner_directions": petitioner,
        "respondent_directions": respondent,
        "your_side_directions": your_side,
        "other_side_directions": other_side,
        "your_side_label": your_label,
        "other_side_label": other_label,
        "party_role": role,
        "next_date": order.summary_next_date,
        "next_date_purpose": order.summary_next_date_purpose,
        "is_routine_adjournment": order.summary_is_routine_adjournment,
        "generated_at": order.summary_generated_at,
        "error": order.summary_error,
    }
