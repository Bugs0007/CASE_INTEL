"""Carry every existing sign-in over to the new per-session tokens.

Each DRF authtoken.Token becomes one AuthSession whose key hash is the hash
of that same key, so a browser still holding it stays signed in through the
deploy -- nobody has to log in again. That carried-over session behaves like
the old token did (every device that had the key shares it) until the user
next signs in, which gives that device its own session; it then expires
after AUTH_SESSION_IDLE_DAYS without use like any other.

The Token rows are left in place, unused by the new authentication class:
if this release is rolled back, the old code finds them and nobody is
signed out. Delete them once the release has settled (see the report).

Reverse removes only the carried-over sessions.
"""

import hashlib
from datetime import timedelta

from django.db import migrations
from django.utils import timezone

IDLE_DAYS = 7  # AUTH_SESSION_IDLE_DAYS' default; the first request slides it anyway


def carry_over(apps, schema_editor):
    Token = apps.get_model("authtoken", "Token")
    AuthSession = apps.get_model("core", "AuthSession")
    now = timezone.now()
    sessions = [
        AuthSession(
            user_id=token.user_id,
            key_hash=hashlib.sha256(token.key.encode("utf-8")).hexdigest(),
            source="legacy",
            last_used_at=now,
            expires_at=now + timedelta(days=IDLE_DAYS),
        )
        for token in Token.objects.all().iterator()
    ]
    AuthSession.objects.bulk_create(sessions, ignore_conflicts=True)
    if sessions:
        print(f"\n  Carried {len(sessions)} existing sign-in(s) over to per-session tokens.")


def remove_carried_over(apps, schema_editor):
    apps.get_model("core", "AuthSession").objects.filter(source="legacy").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0040_auth_sessions"),
        ("authtoken", "0004_alter_tokenproxy_options"),
    ]

    operations = [
        migrations.RunPython(carry_over, remove_carried_over),
    ]
