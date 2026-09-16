# Case Intel systemd units

Reference copies of the systemd units the production box runs. `deploy/provision.sh`
templates and installs the gunicorn (`case-intel`) and worker (`case-intel-worker`)
units itself; the cause-list timer here is installed by hand (below) because it is
per-court and rarely changes.

| Unit | What it runs | Installed by |
|------|--------------|--------------|
| `case-intel.service` | gunicorn (web) | `provision.sh` |
| `case-intel-worker.service` | `manage.py process_jobs` | `provision.sh` |
| `case-intel-causelist@.service` + `.timer` | `manage.py fetch_cause_lists --court <key>` | **manually, see below** |

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
