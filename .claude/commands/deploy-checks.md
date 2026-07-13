---
description: Run the pre-deploy Django checks (system check, migration status, collectstatic) for Case Intel
---

Run these steps in order, stopping and reporting if any step fails:

1. `python manage.py check` — catch settings/config errors before anything else.
2. `python manage.py showmigrations` — confirm which migrations are already applied vs. pending; call out any pending migration that touches `DocumentChunk`, `HnswIndex`, or `embedding` fields specifically, since those are expensive on production RDS (see the embedding-dimension gotcha in CLAUDE.md) — flag it to the user before applying rather than running blind.
3. `python manage.py migrate` — apply pending migrations.
4. `python manage.py collectstatic --noinput` — collect static files.

After these complete, remind the user that **this project has no documented process-restart step** (no systemd unit, Procfile, or Dockerfile found in the repo as of this setup) — whatever restarts gunicorn/the app server on the EC2 host (`13.204.122.149` / `caseintel.duckdns.org`) needs to be run separately, and ask them how that's actually done if it isn't already known, so this command can be extended to include it.
