# Case Intel systemd units

Reference copies of the systemd units the production box runs. `deploy/provision.sh`
templates and installs the gunicorn (`case-intel`) and worker (`case-intel-worker`)
units itself; the cause-list timer here is installed by hand (below) because it is
per-court and rarely changes.

| Unit | What it runs | Installed by |
|------|--------------|--------------|
| `case-intel.service` | gunicorn (web) | `provision.sh` |
| `case-intel-worker.service` | `manage.py process_jobs` | `provision.sh` |
| `case-intel-search-worker.service` | `manage.py process_jobs --lane search` (optional) | `provision.sh` with `ENABLE_SEARCH_WORKER=true` — **off by default, measure first (below)** |
| `case-intel-causelist@.service` + `.timer` | `manage.py fetch_cause_lists --court <key>` | **manually, see below** |

## Search worker (optional second worker)

One advocate search runs 10–45 minutes. With a single worker (`--lane all`, the
default) nothing else is picked up meanwhile — no order check, refresh-all, upload or
briefing — and a refresh-all queued ahead of a search delays it. `process_jobs` has
lanes to split that:

| Lane | Claims | Run it as |
|------|--------|-----------|
| `all` (default) | every job type | the single worker |
| `search` | `advocate_search`, `advocate_import` | `case-intel-search-worker` |
| `portal` | documents, briefings, order sync, refresh-all | `case-intel-worker`, once the search worker exists |
| `interactive` | documents and briefings only | an optional extra, unchanged |

Run **both** `search` and `portal`, or neither: a lone `search` worker leaves order sync
and uploads queued forever, a lone `portal` worker leaves every search queued. A test
pins that every job type belongs to exactly one of the two.

### It costs memory — measure before enabling

Each worker process holds its own copy of the CAPTCHA OCR model. On a developer
machine a search worker measured about 60 MB after start-up and about 135 MB after its
first CAPTCHA (so roughly +75 MB for the model); both workers recycle themselves past
`WORKER_MAX_RSS_MB` (default 300) between jobs, so one can grow to ~300 MB. The
production box was **not** measured from the development machine. On the box, with the
single worker idle and then during a search:

```bash
free -m                                           # the "available" column is what is really free
ps -o pid,rss,cmd -C python | grep process_jobs  # RSS in KB, per worker
systemctl show case-intel-worker -p MemoryCurrent # bytes, if cgroup accounting is on
```

**Rule:** enable the second worker only if at least 400 MB stays free with it running.
Allowing for the new worker to reach its 300 MB recycle limit, that means `available`
should be about 700 MB or more *before* you start it (about 530 MB if you only count
its typical ~130 MB). If it is tighter than that, leave the single worker in place.

### Enable

```bash
# in deploy/provision.env (or the environment):  ENABLE_SEARCH_WORKER=true
sudo ./deploy/provision.sh     # idempotent: rewrites the worker unit with --lane portal,
                               # writes case-intel-search-worker, extends the sudoers rule
sudo systemctl daemon-reload
sudo systemctl restart case-intel-worker
sudo systemctl start case-intel-search-worker
```

`.github/workflows/deploy.yml` restarts only `case-intel` and `case-intel-worker`; add
`case-intel-search-worker` to its restart step (this repo's workflow was not changed).
Watch `free -m` for a day. To go back: `sudo systemctl disable --now
case-intel-search-worker`, re-run `provision.sh` without the flag (the main worker returns
to `--lane all`) and restart it.

### Speed flag (OFF)

`ADVOCATE_SEARCH_REUSE_SESSION=true` in `.env` starts the portal session once per district
instead of once per court complex (and again after any failure). It is **off by default**:
switch it on after reading the timing numbers from your own box. Each search logs one
`Advocate search timing …` line per court complex (district and complex *codes*, seconds
per step, attempts, outcome) and ends with a summary in the Activity log entry and in the
job's `payload["timing"]`, so before and after are comparable on the same district. A
second flag that resubmitted after a wrong CAPTCHA without restarting the session was tried
and removed: the portal rejects it ("Invalid Request"), which made each retry slower.

## Cause-list timer

The cause-list fetch used to be two hand-added crontab lines. It is now a pair of
**instance-templated** systemd units — `%i` is a court registry key from
`core/services/cause_list/registry.py` (`telangana_hc` is the only one today).

### Install (one-time, per court)

```bash
cd /home/ubuntu/CASE_INTEL          # PROJECT_DIR
sudo cp deploy/systemd/case-intel-causelist@.service /etc/systemd/system/
sudo cp deploy/systemd/case-intel-causelist@.timer   /etc/systemd/system/
sudo systemctl daemon-reload

# smoke-test the wiring first (no network, no DB writes):
.venv/bin/python manage.py fetch_cause_lists --check

# then enable the timer for each court in settings.CAUSE_LIST_COURTS:
sudo systemctl enable --now case-intel-causelist@telangana_hc.timer
```

Check `User`/`Group`/`WorkingDirectory`/`ExecStart` paths in
`case-intel-causelist@.service` match the box (defaults assume
`ubuntu` + `/home/ubuntu/CASE_INTEL`, same as the other units).

### Remove the old crontab entries

This change **replaces** the manual cron pair. After the timer is enabled, drop them:

```bash
crontab -e
# delete these two lines (or whatever times were used):
#   0 19 * * *   cd /home/ubuntu/CASE_INTEL && .venv/bin/python manage.py fetch_cause_lists
#   30 6 * * *   cd /home/ubuntu/CASE_INTEL && .venv/bin/python manage.py fetch_cause_lists
```

### Verify

```bash
systemctl list-timers 'case-intel-causelist@*'      # next/last run
journalctl -u 'case-intel-causelist@telangana_hc.service' --since today
systemctl start case-intel-causelist@telangana_hc.service   # run once now
```

### Adding a court later

1. Write a fetcher module (see `core/services/cause_list/telangana_hc.py`).
2. Add a `CauseListCourt(...)` entry in `core/services/cause_list/registry.py`.
3. Add its key to `CAUSE_LIST_COURTS` in the box's `.env`.
4. `sudo systemctl enable --now case-intel-causelist@<newkey>.timer`

The unit files are **not** edited — they are templated on the key.
