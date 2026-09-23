"""Client emails as drafts: "your matter was heard" updates and payment
reminders, written by the system, edited and sent only by the advocate.

  compose.py  -- the plain-language text (pure)
  service.py  -- idempotent draft creation, one per hearing event / reminder
  send.py     -- editing, sending (through core/services/email_delivery.py)
                 and discarding a draft
"""

from .send import (
    ClientMessageError,
    InvoiceAlreadyPaidError,
    NoRecipientsError,
    NotADraftError,
    discard_client_message,
    eligible_contacts,
    send_client_message,
    set_recipients,
)
from .service import (
    MAX_REMINDERS,
    draft_case_update,
    draft_payment_reminder,
    draft_update_for_order,
    draft_update_for_reschedule,
    draft_updates_for_new_dates,
    next_reminder_due,
)

__all__ = [
    "ClientMessageError",
    "InvoiceAlreadyPaidError",
    "MAX_REMINDERS",
    "NoRecipientsError",
    "NotADraftError",
    "discard_client_message",
    "draft_case_update",
    "draft_payment_reminder",
    "draft_update_for_order",
    "draft_update_for_reschedule",
    "draft_updates_for_new_dates",
    "eligible_contacts",
    "next_reminder_due",
    "send_client_message",
    "set_recipients",
]
