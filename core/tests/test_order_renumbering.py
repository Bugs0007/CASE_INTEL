"""The same court order stored twice under two numbers -- regression tests
on the real WP/26147/2026 capture (see fixtures/ecourts/README.md).

The portal numbers a case's orders by position. WP/26147/2026 was first
synced while it listed {1: 07 Aug, 2: 14 Aug}; the 13 Aug order was
uploaded later, after which it listed {1: 07 Aug, 2: 13 Aug, 3: 14 Aug,
4: 17 Aug}. With identity = number + date, the 14 Aug order was downloaded
again as "3" beside the stored "2", and "Order 2" showed on two hearings.
"""

import importlib
import re
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.apps import apps as global_apps
from django.contrib.auth.models import User

from core.models import Case, ClientMessage, CourtOrder, Document, Task
from core.services.court_data.ecourts_parsing import _parse_hc_orders
from core.services.court_order_sync import sync_case_orders

FIXTURES = Path(__file__).parent / "fixtures" / "ecourts"
CNR = "HBHC010536082026"
LIVE_HTML = (FIXTURES / "hc_cnr_HBHC010536082026.html").read_text(encoding="utf-8")
ORDER_3_TEXT = (FIXTURES / "order_HBHC010536082026_3_2026-08-14.txt").read_text(encoding="utf-8")
ORDER_4_TEXT = (FIXTURES / "order_HBHC010536082026_4_2026-08-17.txt").read_text(encoding="utf-8")


def _listing_before_the_late_upload(html: str) -> str:
    """The page as the portal showed it before the 13 Aug order was
    uploaded: that row gone, the later ones one number lower."""
    rows = re.findall(r"<tr><td style='border-top:none;'>.*?</tr>", html, flags=re.S)
    assert len(rows) == 4, "the capture lists four orders"
    thirteenth = next(r for r in rows if "13-08-2026" in r)
    html = html.replace(thirteenth, "")
    for old, new in (("3", "2"), ("4", "3")):
        html = html.replace(
            f"<tr><td style='border-top:none;'>&nbsp;&nbsp;{old}</td>",
            f"<tr><td style='border-top:none;'>&nbsp;&nbsp;{new}</td>",
        )
    return html


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="renumber-advocate", password="pw-12345")


@pytest.fixture
def case(advocate):
    return Case.objects.create(
        owner=advocate,
        case_number="WP/26147/2026",
        title="S.Sashi Kumar vs The State of Telangana",
        client_name="S.Sashi Kumar",
        cnr_number=CNR,
        court_type="high_court",
        tracking_enabled=True,
        tracking_config={"court_type": "high_court", "cnr": CNR},
    )


def _provider_listing(html):
    provider = MagicMock()
    provider.list_orders.side_effect = lambda config: [r for r, _ in _parse_hc_orders(html, CNR)]
    provider.download_order.side_effect = lambda config, record: b"%PDF-1.7 order " + record.dedup_key.encode()
    return provider


def _sync(case, html):
    with patch("core.services.court_order_sync.get_provider", return_value=_provider_listing(html)), \
            patch("core.services.court_order_sync.default_storage") as storage, \
            patch("core.services.court_order_sync.time.sleep"):
        storage.save.side_effect = lambda name, content: name
        return sync_case_orders(case)


def _labels(case):
    return sorted((o.order_number, o.order_date) for o in CourtOrder.objects.filter(case=case))


class TestTheCapture:
    def test_lists_four_orders_numbered_by_date(self):
        records = [r for r, _ in _parse_hc_orders(LIVE_HTML, CNR)]
        assert [(r.order_number, r.order_date) for r in records] == [
            ("1", date(2026, 8, 7)),
            ("2", date(2026, 8, 13)),
            ("3", date(2026, 8, 14)),
            ("4", date(2026, 8, 17)),
        ]

    def test_the_earlier_listing_had_the_14_aug_order_as_number_2(self):
        records = [r for r, _ in _parse_hc_orders(_listing_before_the_late_upload(LIVE_HTML), CNR)]
        assert [(r.order_number, r.order_date) for r in records] == [
            ("1", date(2026, 8, 7)),
            ("2", date(2026, 8, 14)),
            ("3", date(2026, 8, 17)),
        ]


@pytest.mark.django_db
class TestSyncAcrossTheRenumbering:
    def test_a_renumbered_order_is_relabelled_not_downloaded_again(self, case):
        first = _sync(case, _listing_before_the_late_upload(LIVE_HTML))
        assert first["downloaded"] == 3
        fourteenth = CourtOrder.objects.get(case=case, order_date=date(2026, 8, 14))
        assert fourteenth.order_number == "2"

        second = _sync(case, LIVE_HTML)

        # Only the late 13 Aug order is new; 14 and 17 Aug were renumbered.
        assert second["downloaded"] == 1
        assert second["relabelled"] == 2
        assert _labels(case) == [
            ("1", date(2026, 8, 7)),
            ("2", date(2026, 8, 13)),
            ("3", date(2026, 8, 14)),
            ("4", date(2026, 8, 17)),
        ]
        fourteenth.refresh_from_db()
        assert fourteenth.order_number == "3"  # the same row, same document
        assert fourteenth.dedup_key == f"{CNR}:3:2026-08-14"
        assert Document.objects.filter(case=case).count() == 4

    def test_a_steady_listing_changes_nothing(self, case):
        _sync(case, LIVE_HTML)
        again = _sync(case, LIVE_HTML)
        assert (again["downloaded"], again["relabelled"]) == (0, 0)
        assert CourtOrder.objects.filter(case=case).count() == 4

    def test_a_re_dated_order_with_the_same_text_is_relabelled(self, case):
        """The other way one number can carry two dates: the portal
        corrects an order's date. Only identical text proves it."""
        _sync(case, _listing_before_the_late_upload(LIVE_HTML))
        held = CourtOrder.objects.get(case=case, order_number="2")
        Document.objects.filter(id=held.document_id).update(extracted_text=ORDER_3_TEXT * 3)
        corrected = _listing_before_the_late_upload(LIVE_HTML).replace("14-08-2026", "15-08-2026")

        with patch("core.services.court_order_sync._pdf_text", return_value=ORDER_3_TEXT * 3):
            result = _sync(case, corrected)

        assert result["relabelled"] == 1 and result["downloaded"] == 0
        held.refresh_from_db()
        assert held.order_date == date(2026, 8, 15)
        assert CourtOrder.objects.filter(case=case, order_number="2").count() == 1

    def test_a_different_text_under_the_same_number_is_kept_as_new(self, case):
        _sync(case, _listing_before_the_late_upload(LIVE_HTML))
        held = CourtOrder.objects.get(case=case, order_number="2")
        Document.objects.filter(id=held.document_id).update(extracted_text=ORDER_3_TEXT * 3)
        corrected = _listing_before_the_late_upload(LIVE_HTML).replace("14-08-2026", "15-08-2026")

        with patch("core.services.court_order_sync._pdf_text", return_value=ORDER_4_TEXT):
            result = _sync(case, corrected)

        assert result["downloaded"] == 1 and result["relabelled"] == 0


_dedupe = importlib.import_module("core.migrations.0037_dedupe_court_orders")


def _stored(case, number, day, text, **extra):
    document = Document.objects.create(
        owner=case.owner, case=case, filename=f"{CNR}_order_{number}_{day}.pdf",
        file_path=f"documents/court_orders/{CNR}_order_{number}_{day}.pdf", file_type="pdf",
        document_type="court_order", document_date=day, processing_status="completed",
        extracted_text=text,
    )
    return CourtOrder.objects.create(
        owner=case.owner, case=case, order_number=number, order_date=day,
        dedup_key=f"{CNR}:{number}:{day.isoformat()}", document=document, **extra,
    )


@pytest.mark.django_db
class TestDedupeMigration:
    """What production holds for WP/26147/2026, built the way the old sync
    stored it: the 14 Aug order twice ("2" first, then "3")."""

    def _production_state(self, case):
        old = _stored(
            case, "2", date(2026, 8, 14), ORDER_3_TEXT * 3,
            summary_status=CourtOrder.SUMMARY_NO_DIRECTIONS, summary_what_happened="Listed for orders.",
        )
        thirteenth = _stored(case, "2", date(2026, 8, 13), "Notice before admission. " * 20)
        current = _stored(case, "3", date(2026, 8, 14), ORDER_3_TEXT * 3)
        _stored(case, "4", date(2026, 8, 17), ORDER_4_TEXT)
        return old, thirteenth, current

    def test_removes_the_copy_and_keeps_the_correctly_numbered_row(self, case):
        old, thirteenth, current = self._production_state(case)
        message = ClientMessage.objects.create(
            owner=case.owner, case=case, kind="case_update", dedup_key="case_update:x:2026-08-14",
            subject="s", body="b", court_order=old,
        )
        task = Task.objects.create(owner=case.owner, case=case, title="File counter", source_order=old)

        _dedupe.dedupe(global_apps, None)

        assert _labels(case) == [
            ("2", date(2026, 8, 13)),
            ("3", date(2026, 8, 14)),
            ("4", date(2026, 8, 17)),
        ]
        assert not Document.objects.filter(id=old.document_id).exists()
        current.refresh_from_db()
        # The survivor had no summary of its own: the copy's moves over.
        assert current.summary_status == CourtOrder.SUMMARY_NO_DIRECTIONS
        assert current.summary_what_happened == "Listed for orders."
        message.refresh_from_db()
        task.refresh_from_db()
        assert message.court_order_id == current.id
        assert task.source_order_id == current.id

    def test_the_renumbering_signature_alone_is_enough_for_an_unreadable_copy(self, case):
        old = _stored(case, "2", date(2026, 8, 14), "")
        _stored(case, "2", date(2026, 8, 13), "")
        current = _stored(case, "3", date(2026, 8, 14), "")

        _dedupe.dedupe(global_apps, None)

        assert not CourtOrder.objects.filter(id=old.id).exists()
        assert CourtOrder.objects.filter(id=current.id).exists()

    def test_readable_but_different_orders_are_never_merged(self, case):
        old = _stored(case, "2", date(2026, 8, 14), ORDER_4_TEXT)
        _stored(case, "2", date(2026, 8, 13), "Notice before admission. " * 20)
        _stored(case, "3", date(2026, 8, 14), ORDER_3_TEXT * 3)

        _dedupe.dedupe(global_apps, None)

        assert CourtOrder.objects.filter(id=old.id).exists()

    def test_another_owners_orders_are_not_touched(self, case):
        other = User.objects.create_user(username="other-renumber", password="pw-12345")
        other_case = Case.objects.create(
            owner=other, case_number="WP/1/2026", title="t", client_name="c", cnr_number="HBHC010000012026"
        )
        _stored(other_case, "2", date(2026, 8, 13), "a" * 300)
        self._production_state(case)

        _dedupe.dedupe(global_apps, None)

        assert CourtOrder.objects.filter(case=other_case).count() == 1
