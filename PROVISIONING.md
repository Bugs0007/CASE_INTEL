# Provisioning a new Case Intel server

Full path from "I have a fresh AWS account" to "the app is live", for a new
customer/environment. Steps marked **[manual]** genuinely cannot be scripted
from inside the instance or need an external account action -- everything
else is `deploy/provision.sh`.

## 1. Create the database **[manual]**

- Create an RDS PostgreSQL instance (the production one is
  `case-intel-db.cru26wowwqp8.ap-south-1.rds.amazonaws.com`, ap-south-1).
- Enable the `pgvector` extension on it (`CREATE EXTENSION vector;` once
  connected, requires an RDS parameter group that allows `pgvector` -- recent
  RDS Postgres versions support it out of the box).
- Create the application database and a user for it. Note the host, port,
  database name, username, and password -- they go in `.env` in step 5.

Why manual: this is an AWS account-level resource with its own lifecycle
(backups, security groups, parameter groups) independent of any single EC2
box; provisioning it from inside a not-yet-existing EC2 instance is circular.

## 2. Create the EC2 instance **[manual]**

- Launch an Ubuntu 24.04 LTS instance (the current production box is
  `13.204.122.149`).
- Attach/create a security group and open **22 (SSH), 80 (HTTP), 443
  (HTTPS)** -- `deploy/provision.sh` prints this reminder again at the end,
  but it cannot open these itself since security groups are an AWS API
  concept, not something configurable from inside the instance.
- Make sure the EC2 instance's outbound rules (or NAT/route table, if it's in
  a private subnet) allow it to reach the RDS instance from step 1.

## 3. Point DNS at the instance **[manual]**

- The production domain is `caseintel.duckdns.org` (DuckDNS, chosen because
  it's free and EC2 doesn't have a static hostname by default). For a new
  customer, either reuse DuckDNS with a new subdomain or point a real domain
  you own at the instance's public IP.
- This has to happen *before* requesting a TLS cert in step 6 -- Let's
  Encrypt's HTTP-01 challenge needs the domain to already resolve to the box.

## 4. Run `provision.sh`

SSH into the new instance, clone the repo (or just copy `deploy/provision.sh`
and `deploy/provision.env.example` over -- the script itself clones the repo
for you), then:

```bash
cp deploy/provision.env.example deploy/provision.env
# edit deploy/provision.env: set DOMAIN to the domain from step 3,
# GIT_REPO_URL if this is a fork, DEPLOY_USER if not "ubuntu"
sudo ./deploy/provision.sh
```

This installs system packages (including `tesseract-ocr` and `ghostscript`,
which `ocrmypdf` needs for scanned-document OCR -- pip alone is not enough),
sets up a 1GB swap file, clones the repo, creates the venv and installs
`requirements.txt`, installs Ollama and pulls `nomic-embed-text`, downloads
the spaCy `en_core_web_sm` model, writes and enables the `case-intel`
gunicorn systemd unit (`--preload --workers 2 --timeout 120`, matching
production), writes and enables the `case-intel-worker` unit (the
`manage.py process_jobs` background document-processing worker -- see
`deploy/case-intel-worker.service` for the reference copy; document uploads
only enqueue a job, so without this service running nothing ever gets
chunked/embedded), writes and enables the Nginx site for your domain, and
writes a narrow sudoers rule letting the deploy user run only
`sudo systemctl restart case-intel` and
`sudo systemctl restart case-intel-worker` without a password (not the broad
`NOPASSWD: ALL` that's on the current production box today -- see the
CACHES/Celery changes in this same session for context on tightening things
that were more permissive than needed).

It is idempotent -- safe to re-run if a step fails partway through.

**Do not run this against the existing production instance** (`13.204.122.149`
/ `caseintel.duckdns.org`) -- it's already provisioned. This is for new boxes
only.

## 5. Fill in `.env` **[manual]**

`provision.sh` clones the repo but cannot write secrets into it. On the
instance:

```bash
cd ~/CASE_INTEL   # or wherever provision.env's PROJECT_DIR pointed
cp .env.example .env
nano .env
```

Fill in at minimum: `SECRET_KEY` (generate a fresh one, don't reuse the repo
default), `DEBUG=False`, `ALLOWED_HOSTS` (the domain + the instance's public
IP), the RDS `DB_*` values from step 1, and either the Ollama or
OpenAI/Groq AI provider variables depending on which this deployment uses.
See `CLAUDE.md` for what each toggle (`USE_OLLAMA`, `USE_GROQ`) actually
controls, and note the embedding-dimension gotcha there before ever setting
`USE_OLLAMA=false` in a real deployment.

Then bring the app up for the first time:

```bash
source .venv/bin/activate
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl start case-intel
sudo systemctl start case-intel-worker
sudo systemctl status case-intel          # confirm it's actually running
sudo systemctl status case-intel-worker   # ditto -- uploads stay "queued" forever without it
```

If `/static/` or `/media/` 404 through Nginx, check that the Nginx worker
process (`www-data`) can actually read into the project directory --
`provision.sh` doesn't change directory permissions on your home directory,
and a `chmod 700` home dir will block Nginx's `alias` even though gunicorn
(running as the deploy user) works fine.

## 6. Issue the TLS certificate **[manual]**

Only after step 3's DNS actually resolves to this box:

```bash
sudo certbot --nginx -d your-domain-here
```

`provision.sh` deliberately does not run this itself -- certbot's HTTP-01
challenge will fail on a domain that isn't resolving yet, and running it
automatically as part of provisioning would make the script fail on every
fresh box before DNS has propagated.

## 7. Add GitHub Actions secrets **[manual]**

In the repo's Settings -> Secrets and variables -> Actions, add:

- `EC2_HOST` -- the instance's IP or domain
- `EC2_USERNAME` -- the `DEPLOY_USER` from `provision.env` (e.g. `ubuntu`)
- `EC2_SSH_KEY` -- the private key for that user

This can't be scripted from inside the instance -- it's GitHub repo
configuration, not server state.

## 8. First deploy

Push to `main` (or re-run the `Deploy to EC2` workflow manually). See
`.github/workflows/deploy.yml` and `.claude/commands/deploy-checks.md` for
exactly what it runs. It only updates code and restarts the service -- it
assumes everything in steps 1-7 above is already done.

## What's NOT in this repo, and why

- **No RDS/database creation** -- AWS account-level resource, see step 1.
- **No DNS/DuckDNS setup** -- external account action, see step 3.
- **No certbot cert issuance** -- needs a resolving domain first, see step 6.
- **No GitHub secrets configuration** -- GitHub repo settings, see step 7.

These are the genuinely unavoidable manual steps even with `provision.sh` in
hand: creating the RDS instance, creating the EC2 instance, pointing DNS,
filling in `.env` secrets, running `certbot` once, and adding the three
GitHub Actions secrets. Everything else -- every package, service, and config
file on the box itself -- is now `deploy/provision.sh`, not a remembered
sequence of SSH commands.
