"""Start Django once, before anything imports a model."""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "case_intel_project.settings")

from django.apps import apps  # noqa: E402

if not apps.ready:
    django.setup()
