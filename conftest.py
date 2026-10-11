"""Repo-wide pytest guards.

Test-database host guard
------------------------
pytest-django builds its test database on whatever server
``DATABASES["default"]`` points at: it CREATEs ``test_<DB_NAME>`` there and
DROPs it at the end of the run. Settings read ``DB_HOST`` from ``.env``
(python-decouple), and a developer ``.env`` copied from the production box
points at the production RDS instance. Running ``pytest`` from anywhere that
can reach that host would create and drop a database on the production
server.

So every DB-backed test refuses to start unless the database host is local.
Tests that don't touch the database are unaffected and still run anywhere.

To run the DB tests, point them at a local Postgres (with the pgvector
extension available) via environment variables, which python-decouple reads
ahead of ``.env``::

    DB_HOST=localhost DB_PORT=5432 DB_USER=postgres DB_PASSWORD=<local> pytest

A non-local host that is genuinely a disposable test server (a CI service
container reachable by name, say) can be allowed explicitly with
``ALLOW_REMOTE_TEST_DB=1``.
"""

import os

import pytest

_LOCAL_DB_HOSTS = {"", "localhost", "127.0.0.1", "::1"}


def _refuse_non_local_test_db() -> None:
    from django.conf import settings

    host = (settings.DATABASES["default"].get("HOST") or "").strip().lower()
    if host in _LOCAL_DB_HOSTS or os.environ.get("ALLOW_REMOTE_TEST_DB") == "1":
        return
    pytest.fail(
        f"Refusing to build the test database on non-local host {host!r}. "
        "pytest-django would CREATE and DROP a test database on that server. "
        "Point the tests at a local Postgres instead "
        "(e.g. DB_HOST=localhost DB_PASSWORD=<local> pytest), or set "
        "ALLOW_REMOTE_TEST_DB=1 if that host is a disposable test server.",
        pytrace=False,
    )


@pytest.fixture(scope="session")
def django_db_modify_db_settings(django_db_modify_db_settings_parallel_suffix):
    """Runs before pytest-django creates the test database -- the one point
    every DB-backed test passes through, and before any connection opens."""
    _refuse_non_local_test_db()


# ---------------------------------------------------------------------------
# File-storage guard
# ---------------------------------------------------------------------------
# Same hazard as the database host above, for files. settings.py reads
# USE_S3 / AWS_* from .env, and a developer .env copied from the production
# box has USE_S3=true and the production bucket -- so without this, every
# test that writes through default_storage (document and travel uploads,
# invoice and generated PDFs, order sync, the cleanup command's tests...)
# wrote real objects into the production bucket, and the cleanup command's
# tests listed it. Found 2026-10-08: a full run listed 38 real production
# order PDFs; only a fixture error (S3 has no local path()) stopped
# `cleanup_orphaned_order_files --delete` from treating them all as orphans.
#
# Every test therefore gets plain local-disk storage under a temp directory,
# whatever .env says. Tests that want a different MEDIA_ROOT still set their
# own; tests that mock storage still mock it.
@pytest.fixture(autouse=True)
def _tests_never_touch_real_file_storage(settings, tmp_path_factory):
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    settings.MEDIA_ROOT = str(tmp_path_factory.mktemp("media"))
    yield
