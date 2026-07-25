"""Data-migration test for 0019_backfill_title_and_client_contacts.

The migration module's filename starts with a digit, so it can't be
imported with a normal `from core.migrations.0019_... import backfill`
statement (invalid identifier) -- importlib.import_module works the same
way Django's own migration loader loads it. backfill() is called directly
against the live model classes via django.apps.apps, equivalent to what
RunPython passes in since no later migration has altered Case/
ClientContact's shape.
"""

import importlib

import pytest
from django.apps import apps as global_apps
from django.contrib.auth.models import User

from core.models import Case, ClientContact

_migration = importlib.import_module(
    "core.migrations.0019_backfill_title_and_client_contacts"
)


@pytest.fixture
def owner():
    return User.objects.create_user(username="advocate", password="pass-123")


@pytest.mark.django_db
class TestBackfillMigration:
    def test_title_overwritten_with_case_number(self, owner):
        case = Case.objects.create(
            owner=owner,
            case_number="123/2024",
            title="Suresh Kumar vs State Bank",
            client_name="",
        )
        _migration.backfill(global_apps, None)
        case.refresh_from_db()
        assert case.title == "123/2024"

    def test_title_left_alone_when_already_case_number(self, owner):
        case = Case.objects.create(
            owner=owner, case_number="123/2024", title="123/2024", client_name=""
        )
        _migration.backfill(global_apps, None)
        case.refresh_from_db()
        assert case.title == "123/2024"

    def test_non_blank_client_name_creates_billing_contact(self, owner):
        case = Case.objects.create(
            owner=owner,
            case_number="123/2024",
            title="Old Title",
            client_name="  John Smith  ",
        )
        _migration.backfill(global_apps, None)
        contacts = list(ClientContact.objects.filter(case=case))
        assert len(contacts) == 1
        contact = contacts[0]
        assert contact.name == "John Smith"
        assert contact.role == "primary"
        assert contact.is_billing_contact is True
        assert contact.owner_id == owner.id

    def test_blank_client_name_creates_no_contact(self, owner):
        case = Case.objects.create(
            owner=owner, case_number="123/2024", title="Old Title", client_name=""
        )
        _migration.backfill(global_apps, None)
        assert not ClientContact.objects.filter(case=case).exists()

    def test_whitespace_only_client_name_creates_no_contact(self, owner):
        case = Case.objects.create(
            owner=owner, case_number="123/2024", title="Old Title", client_name="   "
        )
        _migration.backfill(global_apps, None)
        assert not ClientContact.objects.filter(case=case).exists()

    def test_unbackfill_is_irreversible(self):
        from django.db.migrations.exceptions import IrreversibleError

        with pytest.raises(IrreversibleError):
            _migration.unbackfill(global_apps, None)
