"""The test suite must never write to real file storage.

A developer .env copied from the production box says USE_S3=true with the
production bucket. conftest.py's autouse fixture forces local disk for every
test; this proves it holds and fails loudly if it ever stops.
"""

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, default_storage, storages


def test_default_storage_is_local_disk_whatever_the_environment_says():
    assert isinstance(storages["default"], FileSystemStorage)
    assert settings.STORAGES["default"]["BACKEND"] == "django.core.files.storage.FileSystemStorage"


def test_saved_files_land_under_the_temp_media_root_and_nowhere_else():
    name = default_storage.save("documents/isolation-check.pdf", ContentFile(b"%PDF-1.4\n%%EOF\n"))
    try:
        assert default_storage.path(name).startswith(str(settings.MEDIA_ROOT))
    finally:
        default_storage.delete(name)
