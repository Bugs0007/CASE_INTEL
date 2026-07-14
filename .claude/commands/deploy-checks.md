---
description: Run the pre-deploy Django checks (system check, migration status, collectstatic) for Case Intel
---

Run these steps in order, stopping and reporting if any step fails:

1. `python manage.py check` — catch settings/config errors before anything else.
2. `python manage.py showmigrations` — confirm which migrations are already applied vs. pending; call out any pending migration that touches `DocumentChunk`, `HnswIndex`, or `embedding` fields specifically, since those are expensive on production RDS (see the embedding-dimension gotcha in CLAUDE.md) — flag it to the user before applying rather than running blind.
3. `python manage.py migrate` — apply pending migrations.
4. `python manage.py collectstatic --noinput` — collect static files.
5. `python -m spacy download en_core_web_sm` — **required after every fresh `pip install`**, not covered by `requirements.txt`. `core/services/document_processor.py` loads this model by name; if it's missing, processing silently degrades to a blank-sentencizer fallback (worse sentence splitting) instead of failing loudly, so it's easy to forget after a clean deploy and not notice for a while.

## What actually happens on deploy (source of truth)

Deploys to production are handled by `.github/workflows/deploy.yml`, triggered on
every push to `main`. It SSHs into the EC2 instance (via `appleboy/ssh-action`,
using the `EC2_HOST` / `EC2_USERNAME` / `EC2_SSH_KEY` repo secrets) and runs, in
order, under `set -e` (stops immediately on the first failed command rather than
restarting the service with a half-applied deploy):

1. `git fetch origin` + `git reset --hard origin/main` — hard reset to an exact
   match of `main`, not `git pull`, so there is no possibility of local drift on
   the server.
2. Activate the venv, `pip install -r requirements.txt`.
3. `python manage.py migrate --noinput`
4. `python manage.py collectstatic --noinput`
5. `sudo systemctl restart case-intel` — the systemd unit (gunicorn behind Nginx)
   that was created manually on the server and is **not** in this repo.

**The current workflow does NOT run `python -m spacy download en_core_web_sm`.**
Since `pip install -r requirements.txt` does not fetch spaCy language models,
every deploy that reinstalls dependencies into a clean environment (or otherwise
loses the previously-downloaded model) needs this step added to `deploy.yml`, or
run manually on the server — it is not automatic today.

**Known gaps to verify before trusting this workflow on a real deploy:**
- The `PROJECT_DIR` and `VENV_DIR` values at the top of `deploy.yml`'s script are
  best guesses (`~/CASE_INTEL`, `.venv`) — confirm they match the actual server
  layout.
- `sudo systemctl restart case-intel` requires the SSH user to have passwordless
  sudo for that specific command — unverified.
- `git reset --hard` will discard any uncommitted changes that exist directly on
  the server — if anyone has ever hotfixed EC2 by hand outside of git, that work
  is destroyed on the next deploy.
- The workflow does not run `python -m spacy download en_core_web_sm` (see above).
