"""
Seed (or verify) a realistic-looking but entirely fictional demo caseload
for a demo user, for demos/screenshots.

Dry-run by default -- it only prints a summary of what would be created and
touches no data. Pass --commit to actually write.

Idempotent: cases/hearings/documents are matched against what already
exists (by case_number / (case, hearing_date, source) / (owner, case,
filename)) and left alone on re-run rather than duplicated. Only the demo
user's own rows are ever touched -- no other user or case is read or
modified.

Usage:
    python manage.py seed_demo_data                  # dry run, prints summary only
    python manage.py seed_demo_data --commit          # actually writes to the database
    python manage.py seed_demo_data --commit --password 'Something123!'
"""

import datetime

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import Case, Document, Hearing

DEFAULT_USERNAME = "account2"
DEFAULT_PASSWORD = "DemoPass2026!"
DEFAULT_EMAIL = "account2@demo.caseintel.local"

TODAY = timezone.localdate()


def _d(offset_days):
    """A date `offset_days` from today (negative = past)."""
    return TODAY + datetime.timedelta(days=offset_days)


def _hearing_datetime(offset_days, hour=10, minute=30):
    naive = datetime.datetime.combine(_d(offset_days), datetime.time(hour, minute))
    return timezone.make_aware(naive)


# All cases/hearings/documents below are fictional -- names, companies and
# facts are invented for demo purposes only and do not reference any real
# client, party or matter.
CASES = [
    {
        "case_number": "DEMO-2026-CV-001",
        "title": "Sharma Textiles Pvt. Ltd. vs. Meridian Logistics Pvt. Ltd.",
        "client_name": "Sharma Textiles Pvt. Ltd.",
        "opposing_party": "Meridian Logistics Pvt. Ltd.",
        "case_type": "civil",
        "status": "open",
        "priority": "high",
        "filing_date": _d(-260),
        "court_type": "district",
        "user_party_role": "petitioner",
        "notes": "[DEMO DATA] Breach of contract -- delayed and damaged consignment of textile goods.",
        "hearings": [
            {"offset": -40, "hearing_type": "motion", "status": "completed",
             "outcome": "Interim stay granted pending discovery.", "judge": "Justice A. Rao"},
            {"offset": 21, "hearing_type": "trial", "status": "scheduled", "judge": "Justice A. Rao"},
        ],
        "documents": [
            {"filename": "plaint_sharma_textiles_v_meridian.pdf", "document_type": "pleading"},
            {"filename": "interim_order_2026_03_18.pdf", "document_type": "order"},
        ],
    },
    {
        "case_number": "DEMO-2026-CR-002",
        "title": "State vs. Arjun Malhotra",
        "client_name": "Arjun Malhotra",
        "opposing_party": "State",
        "case_type": "criminal",
        "status": "open",
        "priority": "critical",
        "filing_date": _d(-95),
        "court_type": "district",
        "user_party_role": "respondent",
        "notes": "[DEMO DATA] Defense representation, alleged cheque-bounce offense under NI Act.",
        "hearings": [
            {"offset": -14, "hearing_type": "arraignment", "status": "completed",
             "outcome": "Bail granted, next hearing set for framing of charges.", "judge": "Judge S. Kulkarni"},
            {"offset": 10, "hearing_type": "status", "status": "scheduled", "judge": "Judge S. Kulkarni"},
        ],
        "documents": [
            {"filename": "fir_copy_demo_case_002.pdf", "document_type": "evidence"},
            {"filename": "bail_application_malhotra.pdf", "document_type": "motion"},
        ],
    },
    {
        "case_number": "DEMO-2026-FAM-003",
        "title": "Priya Nair vs. Karthik Nair (Divorce Petition)",
        "client_name": "Priya Nair",
        "opposing_party": "Karthik Nair",
        "case_type": "family",
        "status": "pending",
        "priority": "medium",
        "filing_date": _d(-150),
        "court_type": "district",
        "user_party_role": "petitioner",
        "notes": "[DEMO DATA] Mutual consent divorce petition with child custody terms under negotiation.",
        "hearings": [
            {"offset": -30, "hearing_type": "preliminary", "status": "completed",
             "outcome": "First motion recorded; six-month cooling-off period begins.", "judge": "Judge M. Iyer"},
            {"offset": 45, "hearing_type": "status", "status": "scheduled", "judge": "Judge M. Iyer"},
        ],
        "documents": [
            {"filename": "divorce_petition_nair.pdf", "document_type": "pleading"},
            {"filename": "custody_terms_draft_v2.pdf", "document_type": "contract"},
        ],
    },
    {
        "case_number": "DEMO-2026-COM-004",
        "title": "Vertex Innovations Ltd. -- Shareholder Dispute",
        "client_name": "Vertex Innovations Ltd.",
        "opposing_party": "Rakesh Bansal (Minority Shareholder)",
        "case_type": "corporate",
        "status": "open",
        "priority": "medium",
        "filing_date": _d(-70),
        "court_type": "high_court",
        "user_party_role": "respondent",
        "notes": "[DEMO DATA] Oppression and mismanagement petition filed by a minority shareholder.",
        "hearings": [
            {"offset": 15, "hearing_type": "motion", "status": "scheduled", "judge": "Justice R. Chandran"},
        ],
        "documents": [
            {"filename": "shareholder_agreement_vertex.pdf", "document_type": "contract"},
            {"filename": "reply_affidavit_vertex_innovations.pdf", "document_type": "pleading"},
        ],
    },
    {
        "case_number": "DEMO-2026-IP-005",
        "title": "Northstar Apparel vs. Bloom & Co. (Trademark Infringement)",
        "client_name": "Northstar Apparel Pvt. Ltd.",
        "opposing_party": "Bloom & Co. Retail LLP",
        "case_type": "ip",
        "status": "open",
        "priority": "high",
        "filing_date": _d(-40),
        "court_type": "high_court",
        "user_party_role": "petitioner",
        "notes": "[DEMO DATA] Trademark infringement and passing-off claim over a similar logo mark.",
        "hearings": [
            {"offset": 7, "hearing_type": "motion", "status": "scheduled", "judge": "Justice K. Bhat"},
        ],
        "documents": [
            {"filename": "trademark_registration_certificate.pdf", "document_type": "evidence"},
            {"filename": "cease_and_desist_bloom_co.pdf", "document_type": "correspondence"},
        ],
    },
    {
        "case_number": "DEMO-2026-LAB-006",
        "title": "Fernandes vs. Coastal Freight Pvt. Ltd. (Wrongful Termination)",
        "client_name": "Maria Fernandes",
        "opposing_party": "Coastal Freight Pvt. Ltd.",
        "case_type": "labor",
        "status": "closed",
        "priority": "low",
        "filing_date": _d(-420),
        "court_type": "district",
        "user_party_role": "petitioner",
        "notes": "[DEMO DATA] Wrongful termination claim, settled with severance payment.",
        "hearings": [
            {"offset": -365, "hearing_type": "preliminary", "status": "completed",
             "outcome": "Matter referred to conciliation.", "judge": "Presiding Officer T. Das"},
            {"offset": -200, "hearing_type": "other", "status": "completed",
             "outcome": "Settled -- severance package agreed, case closed.", "judge": "Presiding Officer T. Das"},
        ],
        "documents": [
            {"filename": "termination_letter_fernandes.pdf", "document_type": "evidence"},
            {"filename": "settlement_agreement_coastal_freight.pdf", "document_type": "contract"},
        ],
    },
    {
        "case_number": "DEMO-2026-TAX-007",
        "title": "Reddy Constructions -- GST Assessment Appeal",
        "client_name": "Reddy Constructions LLP",
        "opposing_party": "Deputy Commissioner of GST",
        "case_type": "tax",
        "status": "pending",
        "priority": "medium",
        "filing_date": _d(-55),
        "court_type": "high_court",
        "user_party_role": "petitioner",
        "notes": "[DEMO DATA] Appeal against a disputed GST input-credit assessment order.",
        "hearings": [
            {"offset": 30, "hearing_type": "appeal", "status": "scheduled", "judge": "Justice N. Pillai"},
        ],
        "documents": [
            {"filename": "gst_assessment_order_reddy.pdf", "document_type": "order"},
            {"filename": "appeal_memo_reddy_constructions.pdf", "document_type": "pleading"},
        ],
    },
    {
        "case_number": "DEMO-2025-CV-008",
        "title": "Ibrahim Traders vs. Coastal Bank Ltd. (Loan Recovery)",
        "client_name": "Ibrahim Traders",
        "opposing_party": "Coastal Bank Ltd.",
        "case_type": "civil",
        "status": "archived",
        "priority": "low",
        "filing_date": _d(-600),
        "court_type": "district",
        "user_party_role": "respondent",
        "notes": "[DEMO DATA] Loan recovery suit, resolved via one-time settlement; archived.",
        "hearings": [
            {"offset": -520, "hearing_type": "trial", "status": "completed",
             "outcome": "One-time settlement recorded; suit disposed of.", "judge": "Judge V. Menon"},
        ],
        "documents": [
            {"filename": "loan_agreement_ibrahim_traders.pdf", "document_type": "contract"},
            {"filename": "settlement_order_2024_12_02.pdf", "document_type": "order"},
        ],
    },
]


class Command(BaseCommand):
    help = (
        "Seed a fictional demo caseload owned by a demo user (default: "
        "'account2'). Dry-run by default -- pass --commit to actually write."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Actually write to the database. Without this flag, only a summary is printed.",
        )
        parser.add_argument("--username", default=DEFAULT_USERNAME)
        parser.add_argument("--password", default=DEFAULT_PASSWORD)
        parser.add_argument("--email", default=DEFAULT_EMAIL)

    def handle(self, *args, **options):
        commit = options["commit"]
        username = options["username"]
        password = options["password"]
        email = options["email"]

        if commit:
            self.stdout.write(self.style.WARNING("COMMIT MODE -- changes will be written to the database.\n"))
        else:
            self.stdout.write(self.style.WARNING(
                "DRY RUN -- no data will be written. Re-run with --commit to apply these changes.\n"
            ))

        existing_user = User.objects.filter(username=username).first()
        user_will_be_created = existing_user is None

        plan = self._build_plan(existing_user)
        self._print_summary(username, email, user_will_be_created, plan)

        if not commit:
            self.stdout.write(self.style.WARNING(
                "\nNothing was written. Re-run with --commit to apply."
            ))
            return

        with transaction.atomic():
            user, created = User.objects.get_or_create(
                username=username, defaults={"email": email}
            )
            user.set_password(password)
            if email:
                user.email = email
            user.save()

            case_created_count = 0
            hearing_created_count = 0
            document_created_count = 0

            for case_spec in CASES:
                case, case_created = Case.objects.get_or_create(
                    owner=user,
                    case_number=case_spec["case_number"],
                    defaults={
                        "title": case_spec["title"],
                        "client_name": case_spec["client_name"],
                        "opposing_party": case_spec["opposing_party"],
                        "case_type": case_spec["case_type"],
                        "status": case_spec["status"],
                        "priority": case_spec["priority"],
                        "filing_date": case_spec["filing_date"],
                        "notes": case_spec["notes"],
                        "court_type": case_spec["court_type"],
                        "user_party_role": case_spec["user_party_role"],
                    },
                )
                if case_created:
                    case_created_count += 1

                for hearing_spec in case_spec.get("hearings", []):
                    hearing_date = _hearing_datetime(hearing_spec["offset"])
                    _, hearing_created = Hearing.objects.get_or_create(
                        case=case,
                        hearing_date=hearing_date,
                        source="manual",
                        defaults={
                            "owner": user,
                            "hearing_type": hearing_spec["hearing_type"],
                            "status": hearing_spec["status"],
                            "judge": hearing_spec.get("judge", ""),
                            "outcome": hearing_spec.get("outcome", ""),
                        },
                    )
                    if hearing_created:
                        hearing_created_count += 1

                for doc_spec in case_spec.get("documents", []):
                    _, doc_created = Document.objects.get_or_create(
                        owner=user,
                        case=case,
                        filename=doc_spec["filename"],
                        defaults={
                            "file_path": f"demo-seed/{case_spec['case_number']}/{doc_spec['filename']}",
                            "file_type": "pdf",
                            "document_type": doc_spec["document_type"],
                            "document_date": case_spec["filing_date"],
                            # No real file was uploaded and no processing/OCR/
                            # embedding ran -- leave at the default "pending"
                            # so the UI doesn't claim this stub was processed.
                        },
                    )
                    if doc_created:
                        document_created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. User {'created' if created else 'reused'}: "
            f"username='{username}' password='{password}'."
        ))
        self.stdout.write(self.style.SUCCESS(
            f"Cases created: {case_created_count}, Hearings created: {hearing_created_count}, "
            f"Documents created: {document_created_count}."
        ))
        self.stdout.write(
            "Note: seeded documents are metadata-only stubs (no real file was uploaded, "
            "no OCR/embedding ran) -- download/process actions on them will not work."
        )

    def _build_plan(self, existing_user):
        """Read-only comparison of CASES against what already exists, used for
        both the dry-run summary and as a sanity check before committing."""
        existing_case_numbers = set()
        existing_hearing_keys = set()
        existing_document_keys = set()

        if existing_user is not None:
            existing_case_numbers = set(
                Case.objects.filter(
                    owner=existing_user,
                    case_number__in=[c["case_number"] for c in CASES],
                ).values_list("case_number", flat=True)
            )
            case_ids_by_number = dict(
                Case.objects.filter(owner=existing_user, case_number__in=existing_case_numbers)
                .values_list("case_number", "id")
            )
            existing_hearing_keys = set(
                Hearing.objects.filter(
                    owner=existing_user, case_id__in=case_ids_by_number.values(), source="manual"
                ).values_list("case_id", "hearing_date")
            )
            existing_document_keys = set(
                Document.objects.filter(
                    owner=existing_user, case_id__in=case_ids_by_number.values()
                ).values_list("case_id", "filename")
            )
        else:
            case_ids_by_number = {}

        rows = []
        for case_spec in CASES:
            case_exists = case_spec["case_number"] in existing_case_numbers
            case_id = case_ids_by_number.get(case_spec["case_number"])

            hearings_to_create = 0
            for hearing_spec in case_spec.get("hearings", []):
                key = (case_id, _hearing_datetime(hearing_spec["offset"]))
                if not case_exists or key not in existing_hearing_keys:
                    hearings_to_create += 1

            documents_to_create = 0
            for doc_spec in case_spec.get("documents", []):
                key = (case_id, doc_spec["filename"])
                if not case_exists or key not in existing_document_keys:
                    documents_to_create += 1

            rows.append({
                "case_number": case_spec["case_number"],
                "title": case_spec["title"],
                "case_type": case_spec["case_type"],
                "status": case_spec["status"],
                "case_exists": case_exists,
                "hearings_total": len(case_spec.get("hearings", [])),
                "hearings_to_create": hearings_to_create,
                "documents_total": len(case_spec.get("documents", [])),
                "documents_to_create": documents_to_create,
            })
        return rows

    def _print_summary(self, username, email, user_will_be_created, plan):
        self.stdout.write(f"Demo user: '{username}' <{email}>")
        self.stdout.write(
            f"  {'Will be created' if user_will_be_created else 'Already exists -- will be reused'}, "
            "password will be (re)set to the given/default value.\n"
        )

        self.stdout.write("Cases (matched by case_number within this demo user's own cases):")
        cases_to_create = 0
        hearings_to_create = 0
        documents_to_create = 0
        for row in plan:
            state = "exists, reused" if row["case_exists"] else "WILL CREATE"
            if not row["case_exists"]:
                cases_to_create += 1
            hearings_to_create += row["hearings_to_create"]
            documents_to_create += row["documents_to_create"]
            self.stdout.write(
                f"  [{state:14}] {row['case_number']}  ({row['case_type']}, {row['status']}) "
                f"-- {row['title']}"
            )
            self.stdout.write(
                f"                     hearings: {row['hearings_to_create']}/{row['hearings_total']} new, "
                f"documents: {row['documents_to_create']}/{row['documents_total']} new"
            )

        self.stdout.write(
            f"\nTotals: {cases_to_create} case(s), {hearings_to_create} hearing(s), "
            f"{documents_to_create} document(s) to create "
            f"(out of {len(plan)} cases considered)."
        )
