"""ClientContact model + serializer tests.

Multi-tenancy (owner scoping across the API) is covered in
test_multi_tenancy.py's TestClientContactIsolation -- these focus on the
billing-contact-uniqueness save() behavior and the writable "case" FK
scoping in ClientContactSerializer.
"""

import pytest
from django.contrib.auth.models import User

from core.models import Case, ClientContact
from core.serializers import ClientContactSerializer


@pytest.fixture
def owner():
    return User.objects.create_user(username="advocate", password="pass-123")


@pytest.fixture
def case(owner):
    return Case.objects.create(owner=owner, case_number="C-001", title="C-001", client_name="")


@pytest.mark.django_db
class TestBillingContactUniqueness:
    def test_second_billing_contact_demotes_the_first(self, owner, case):
        first = ClientContact.objects.create(
            owner=owner, case=case, name="Alice", is_billing_contact=True
        )
        second = ClientContact.objects.create(
            owner=owner, case=case, name="Bob", is_billing_contact=True
        )

        first.refresh_from_db()
        second.refresh_from_db()
        assert first.is_billing_contact is False
        assert second.is_billing_contact is True

    def test_billing_contact_scoped_per_case_not_global(self, owner, case):
        other_case = Case.objects.create(
            owner=owner, case_number="C-002", title="C-002", client_name=""
        )
        this_case_contact = ClientContact.objects.create(
            owner=owner, case=case, name="Alice", is_billing_contact=True
        )
        other_case_contact = ClientContact.objects.create(
            owner=owner, case=other_case, name="Carol", is_billing_contact=True
        )

        this_case_contact.refresh_from_db()
        other_case_contact.refresh_from_db()
        # Different cases -- setting one as billing must not touch the other.
        assert this_case_contact.is_billing_contact is True
        assert other_case_contact.is_billing_contact is True

    def test_non_billing_contact_does_not_demote_existing_one(self, owner, case):
        billing = ClientContact.objects.create(
            owner=owner, case=case, name="Alice", is_billing_contact=True
        )
        ClientContact.objects.create(
            owner=owner, case=case, name="Bob", role="assistant", is_billing_contact=False
        )

        billing.refresh_from_db()
        assert billing.is_billing_contact is True

    def test_editing_existing_billing_contact_does_not_demote_itself(self, owner, case):
        contact = ClientContact.objects.create(
            owner=owner, case=case, name="Alice", is_billing_contact=True
        )
        contact.name = "Alice Updated"
        contact.save()

        contact.refresh_from_db()
        assert contact.is_billing_contact is True
        assert contact.name == "Alice Updated"


@pytest.mark.django_db
class TestClientContactSerializer:
    def test_case_field_scoped_to_requesting_users_own_cases(self, owner, case):
        other_owner = User.objects.create_user(username="other", password="pass-123")
        other_case = Case.objects.create(
            owner=other_owner, case_number="C-999", title="C-999", client_name=""
        )

        class _Request:
            user = owner

        serializer = ClientContactSerializer(context={"request": _Request()})
        case_ids = set(serializer.fields["case"].queryset.values_list("id", flat=True))
        assert case.id in case_ids
        assert other_case.id not in case_ids

    def test_role_choices(self):
        assert dict(ClientContact.ROLE_CHOICES) == {"primary": "Primary", "assistant": "Assistant"}
