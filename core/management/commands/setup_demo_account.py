"""Create (and later verify) the portfolio demo account.

Two modes, deliberately in one command so the setup step and the
"is it actually demo-ready?" step can't drift apart:

    python manage.py setup_demo_account            # create/ensure the account
    python manage.py setup_demo_account --verify   # report what's in it now

WHY NO PASSWORD LIVES HERE
--------------------------
The account is created with set_unusable_password(). Nothing in this file,
in the repo, or in any commit ever holds a real credential -- the operator
sets one out-of-band afterwards:

    python manage.py changepassword recruiter

An unusable password is not a locked account: changepassword replaces it
with a real hash and login works normally from that point on. Until then
the account genuinely cannot be logged into, which is the safe default for
a row that will exist on a public-facing box before anyone is meant to
reach it.

WHY IT CREATES NO CASES
-----------------------
This is a portfolio showcase, not a seeded demo (contrast
`seed_demo_data`, which invents a fictional caseload). The caseload is
meant to be imported through the real advocate-search UI against the live
eCourts portals, so that every case, hearing, order and CNR in the account
is genuine. This command therefore creates exactly one thing -- the user
(plus, optionally, their own billing letterhead) -- and refuses to invent
case data. --verify exists to check the imported result afterwards.

Idempotent: re-running never clobbers an existing user's password, email,
or profile values that were already set. Safe to run again after the
import to re-print the next-step notes.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import (
    AdvocateProfile,
    AppearanceFee,
    Case,
    CourtOrder,
    Document,
    Hearing,
    ProcessingJob,
)

DEFAULT_USERNAME = "recruiter"


class Command(BaseCommand):
    help = (
        "Create the portfolio demo account (no cases, unusable password), or "
        "with --verify, report whether its imported data looks demo-ready."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default=DEFAULT_USERNAME,
            help=f"Account username (default {DEFAULT_USERNAME!r}).",
        )
        parser.add_argument(
            "--email",
            default="",
            help="Optional email for the account. Only set if currently blank.",
        )
        parser.add_argument(
            "--verify",
            action="store_true",
            help=(
                "Don't create anything -- report the account's current "
                "case/hearing/order/document/fee state and flag whatever is "
                "still missing for a complete demo."
            ),
        )
        # --- Billing letterhead (AdvocateProfile) ---------------------------
        # Invoices render profile.letterhead_name or the literal "Advocate",
        # with a blank address block. That reads as unfinished in a portfolio
        # screenshot, so these are offered here -- but never invented, since
        # a made-up bar registration number could collide with a real one.
        parser.add_argument("--letterhead-name", default="", help="Name/firm on the invoice letterhead.")
        parser.add_argument("--address", default="", help="Letterhead address block (use \\n for line breaks).")
        parser.add_argument("--bar-number", default="", help="Bar Council registration number for the letterhead.")
        parser.add_argument("--default-fee", default=None, help="Default appearance fee amount, e.g. 15000.")
        parser.add_argument("--invoice-prefix", default="", help="Invoice number prefix (default 'INV' -> INV-0001).")

    def handle(self, *args, **options):
        username = options["username"]

        if options["verify"]:
            return self._verify(username)
        return self._setup(username, options)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    @transaction.atomic
    def _setup(self, username: str, options: dict) -> None:
        user, created = User.objects.get_or_create(username=username)

        if created:
            # No password is ever written here -- see the module docstring.
            user.set_unusable_password()
            if options["email"]:
                user.email = options["email"]
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created user {username!r} with an unusable password."))
        else:
            self.stdout.write(f"User {username!r} already exists -- password and email left untouched.")
            if options["email"] and not user.email:
                user.email = options["email"]
                user.save(update_fields=["email"])
                self.stdout.write(f"  Set previously-blank email to {options['email']}.")

        self._apply_profile(user, options)
        self._report_cleanliness(user)
        self._print_next_steps(username, user)

    def _apply_profile(self, user: User, options: dict) -> None:
        """Ensure the billing profile row exists, and fill any letterhead
        fields the caller supplied.

        Only ever fills fields that were passed explicitly -- a re-run
        without flags never blanks values set earlier (or edited through
        PATCH /api/advocate-profile/).
        """
        profile, created = AdvocateProfile.objects.get_or_create(owner=user)

        updates = {}
        if options["letterhead_name"]:
            updates["letterhead_name"] = options["letterhead_name"]
        if options["address"]:
            # argparse hands through a literal backslash-n; turn it into a
            # real newline so the address renders as a multi-line block.
            updates["address"] = options["address"].replace("\\n", "\n")
        if options["bar_number"]:
            updates["bar_registration_number"] = options["bar_number"]
        if options["invoice_prefix"]:
            updates["invoice_prefix"] = options["invoice_prefix"]
        if options["default_fee"] is not None:
            try:
                updates["default_fee_amount"] = Decimal(str(options["default_fee"]))
            except (InvalidOperation, ValueError):
                raise CommandError(f"--default-fee must be a number, got {options['default_fee']!r}.")

        if updates:
            for field, value in updates.items():
                setattr(profile, field, value)
            profile.save(update_fields=[*updates, "updated_at"])

        verb = "Created" if created else "Found"
        self.stdout.write(f"{verb} billing profile (AdvocateProfile) for this account.")
        if updates:
            self.stdout.write(f"  Set: {', '.join(sorted(updates))}.")
        if not profile.letterhead_name:
            self.stdout.write(
                self.style.WARNING(
                    "  Letterhead name is blank -- generated invoices will be headed "
                    "'Advocate' with no address. Set it with --letterhead-name/--address "
                    "or via PATCH /api/advocate-profile/ before demoing an invoice."
                )
            )

    def _report_cleanliness(self, user: User) -> None:
        """This command must never create case data. Say so, out loud, with
        the actual counts -- so a re-run against an already-populated
        account can't be mistaken for having reset it."""
        case_count = Case.objects.filter(owner=user).count()
        if case_count == 0:
            self.stdout.write("Account holds 0 cases -- clean, ready for a live import.")
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Account already holds {case_count} case(s). Nothing was created, "
                    f"changed, or deleted by this command."
                )
            )

    def _print_next_steps(self, username: str, user: User) -> None:
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Next steps (operator, on the EC2 box):"))
        self.stdout.write(f"  1. Set a password:  python manage.py changepassword {username}")
        self.stdout.write("  2. Log in through the frontend and import real cases via")
        self.stdout.write("     Cases -> Search by advocate (live eCourts advocate search).")
        self.stdout.write("  3. Confirm the worker is up so imports/documents actually process:")
        self.stdout.write("     systemctl status case-intel-worker")
        self.stdout.write(f"  4. Check the result:  python manage.py setup_demo_account --verify")
        self.stdout.write("  5. Walk REVIEW_CHECKLIST.md before sharing access.")
        self.stdout.write("")
        self.stdout.write(f"(user id={user.pk}, usable_password={user.has_usable_password()})")

    # ------------------------------------------------------------------
    # Verify
    # ------------------------------------------------------------------

    def _verify(self, username: str) -> None:
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(
                f"No user {username!r}. Run `python manage.py setup_demo_account` first."
            )

        self.stdout.write(self.style.MIGRATE_HEADING(f"Demo readiness for {username!r} (user id={user.pk})"))
        self.stdout.write("")

        cases = Case.objects.filter(owner=user)
        case_count = cases.count()
        tracked = cases.filter(tracking_enabled=True).count()
        with_cnr = cases.exclude(cnr_number__isnull=True).exclude(cnr_number="").count()
        hc_cases = cases.filter(court_type="high_court").count()

        self._line("Cases", case_count, case_count > 0, "import cases via the advocate-search UI")
        self._line("  tracking enabled", tracked, tracked > 0, "confirm tracking during import")
        self._line("  with a CNR on file", with_cnr, with_cnr > 0, "a fetch populates this")
        self._line(
            "  High Court cases", hc_cases, hc_cases > 0,
            "cause lists only cover High Court cases -- a district-only caseload "
            "can never show a cause-list badge",
        )

        hearings = Hearing.objects.filter(owner=user)
        ecourts_hearings = hearings.filter(source="ecourts").count()
        self._line("Hearings (from eCourts)", ecourts_hearings, ecourts_hearings > 0,
                   "populated by the tracking fetch")

        listed = hearings.filter(cause_list_status=Hearing.CAUSE_LIST_LISTED).count()
        checked = hearings.exclude(cause_list_status=Hearing.CAUSE_LIST_NOT_CHECKED).count()
        self._line("  cause-list checked", checked, checked > 0,
                   "run `python manage.py fetch_cause_lists` -- nothing schedules it")
        self._line("  cause-list LISTED", listed, listed > 0,
                   "only true on a day the TS HC actually lists one of these cases")

        docs = Document.objects.filter(owner=user)
        doc_count = docs.count()
        completed = docs.filter(processing_status="completed").count()
        failed = docs.filter(processing_status="failed").count()
        pending = docs.exclude(processing_status__in=["completed", "failed"]).count()
        self._line("Documents", doc_count, doc_count > 0, "order sync downloads these, or upload manually")
        self._line("  processed", completed, doc_count == 0 or completed > 0, "worker must be running")
        if pending:
            self.stdout.write(self.style.WARNING(f"  {pending} still pending/processing -- is the worker up?"))
        if failed:
            self.stdout.write(self.style.ERROR(f"  {failed} FAILED -- check worker logs before demoing."))

        orders = CourtOrder.objects.filter(owner=user)
        order_count = orders.count()
        summarized = orders.filter(summary_status=CourtOrder.SUMMARY_SUMMARIZED).count()
        self._line("Court orders", order_count, order_count > 0,
                   "order sync runs automatically after a tracking fetch; many cases genuinely have none")
        self._line("  with an AI summary", summarized, order_count == 0 or summarized > 0,
                   "generated by the worker after each order PDF is processed")

        fees = AppearanceFee.objects.filter(owner=user)
        fee_count = fees.count()
        invoiced = fees.exclude(invoice_number="").count()
        paid = fees.filter(status=AppearanceFee.STATUS_PAID).count()
        self._line("Appearance fees", fee_count, fee_count > 0, "no UI for this -- create via API/shell")
        self._line("  invoiced", invoiced, invoiced > 0, "POST /api/appearance-fees/<id>/invoice/")
        self._line("  paid", paid, paid > 0, "POST /api/appearance-fees/<id>/mark-paid/ (optional)")

        stuck = ProcessingJob.objects.filter(owner=user, status__in=["queued", "running"]).count()
        job_failed = ProcessingJob.objects.filter(owner=user, status="failed").count()
        if stuck:
            self.stdout.write(self.style.WARNING(
                f"\n{stuck} job(s) still queued/running -- let the worker drain before demoing."
            ))
        if job_failed:
            self.stdout.write(self.style.ERROR(f"{job_failed} job(s) FAILED -- investigate before sharing."))
        if not stuck and not job_failed:
            self.stdout.write(self.style.SUCCESS("\nNo stuck or failed background jobs."))

        profile = AdvocateProfile.objects.filter(owner=user).first()
        if profile is None or not profile.letterhead_name:
            self.stdout.write(self.style.WARNING(
                "Billing letterhead is blank -- invoices will be headed 'Advocate' with no address."
            ))

        self.stdout.write("")
        self.stdout.write("Full click-through list: REVIEW_CHECKLIST.md")

    def _line(self, label: str, count: int, ok: bool, hint: str) -> None:
        mark = self.style.SUCCESS("OK  ") if ok else self.style.WARNING("TODO")
        suffix = "" if ok else f"   <- {hint}"
        self.stdout.write(f"  [{mark}] {label}: {count}{suffix}")
