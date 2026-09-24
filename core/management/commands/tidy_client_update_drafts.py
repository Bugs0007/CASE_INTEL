"""Apply the current draft rules to case-update drafts created before them.

Drafts made under the old rules can be unsendable or stale:
  - no contact on the case can receive them (no opted-in contact with an
    email) -- Send could never work;
  - they report a hearing older than CLIENT_UPDATE_MAX_AGE_DAYS;
  - several stack up on one case (one per back-order from a first sync).

This discards (never deletes) UNTOUCHED case-update drafts in those three
situations, keeping each case's newest one. A draft the advocate edited is
left alone, as are reschedule drafts and payment reminders. Discarded rows
keep their dedup key, so the same draft isn't regenerated.

    python manage.py tidy_client_update_drafts --dry-run
    python manage.py tidy_client_update_drafts [--owner <username>]
"""

from collections import defaultdict

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import ClientMessage
from core.services.client_updates.send import eligible_contacts
from core.services.client_updates.service import is_too_old, max_age_days


class Command(BaseCommand):
    help = "Discard untouched case-update drafts that the current rules would not create."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report only; change nothing.")
        parser.add_argument("--owner", help="Only this advocate's drafts (username).")

    def handle(self, *args, **options):
        drafts = ClientMessage.objects.filter(
            kind=ClientMessage.KIND_CASE_UPDATE,
            status=ClientMessage.STATUS_DRAFT,
            edited_by_user=False,
            event_date__isnull=False,
        ).select_related("case")
        if options["owner"]:
            try:
                drafts = drafts.filter(owner=User.objects.get(username=options["owner"]))
            except User.DoesNotExist:
                raise CommandError(f"No user {options['owner']!r}.") from None

        today = timezone.localdate()
        reasons: dict[int, str] = {}
        by_case = defaultdict(list)
        for draft in drafts:
            if not eligible_contacts(draft):
                reasons[draft.id] = "No client contact with an email can receive this."
            elif is_too_old(draft.event_date, today):
                reasons[draft.id] = f"Reports a hearing more than {max_age_days()} days old."
            else:
                by_case[draft.case_id].append(draft)
        for case_drafts in by_case.values():
            case_drafts.sort(key=lambda d: (d.event_date, d.id), reverse=True)
            for older in case_drafts[1:]:
                reasons[older.id] = "Replaced by a newer update for this case."

        messages = {m.id: m for m in drafts}
        for message_id, reason in sorted(reasons.items()):
            message = messages[message_id]
            self.stdout.write(
                f"{'would discard' if options['dry_run'] else 'discard'} draft {message_id} "
                f"({message.case.case_number}, {message.event_date}): {reason}"
            )
            if not options["dry_run"]:
                ClientMessage.objects.filter(id=message_id, status=ClientMessage.STATUS_DRAFT).update(
                    status=ClientMessage.STATUS_DISCARDED,
                    discard_reason=reason[:255],
                    updated_at=timezone.now(),
                )
        verb = "Would discard" if options["dry_run"] else "Discarded"
        self.stdout.write(self.style.SUCCESS(f"{verb} {len(reasons)} of {len(messages)} untouched case-update drafts."))
