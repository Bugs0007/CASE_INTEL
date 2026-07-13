"""
Create (or update) a user and print their auth token, without going
through the Django admin UI.

Usage:
    python manage.py create_test_user <username> <password> [--email you@example.com]
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from rest_framework.authtoken.models import Token


class Command(BaseCommand):
    help = "Create or update a user and print their DRF auth token."

    def add_arguments(self, parser):
        parser.add_argument("username", type=str)
        parser.add_argument("password", type=str)
        parser.add_argument("--email", type=str, default="")

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]
        email = options["email"]

        if not username or not password:
            raise CommandError("username and password are required")

        user, created = User.objects.get_or_create(
            username=username, defaults={"email": email}
        )
        user.set_password(password)
        if email:
            user.email = email
        user.save()

        token, _ = Token.objects.get_or_create(user=user)

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} user '{username}'"))
        self.stdout.write(f"Token: {token.key}")
