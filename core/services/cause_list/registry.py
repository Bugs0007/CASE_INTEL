"""Registry of the courts whose cause lists the scheduled fetch covers.

Why this exists: cause-list ingestion used to be Telangana-HC-only and
wired straight into `manage.py fetch_cause_lists`, so "add a court" meant
editing the command AND remembering to add another hand-written cron line
on the box. Now the command and the systemd timer
(`deploy/systemd/case-intel-causelist@.{service,timer}`) are both
instance-templated on a court KEY, and turning a court on is:

    1. write a sibling fetcher module (see `telangana_hc.py`) that returns
       a `CauseListDay`,
    2. add a `CauseListCourt(...)` entry to `_ALL_COURTS` below,
    3. list its key in `settings.CAUSE_LIST_COURTS`,
    4. on the server:  systemctl enable --now case-intel-causelist@<key>.timer

Steps 1-3 are code/config in this repo; step 4 is the only server action
and it never changes the timer unit itself.

Keeping this deliberately small: the `cause_list` package docstring is
right that a universal parser is a mistake. This is a lookup table, not an
abstraction layer -- every court still gets its own hand-written fetcher.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Callable

from django.conf import settings

from .exceptions import CauseListNotConfiguredError
from .telangana_hc import COURT_KEY as _TELANGANA_HC_KEY
from .telangana_hc import COURT_LABEL as _TELANGANA_HC_LABEL

if TYPE_CHECKING:  # pragma: no cover
    from .telangana_hc import CauseListDay

# systemd instance names (and the --court CLI value) must be a plain token.
_KEY_RE = re.compile(r"^[a-z0-9_]+$")


def _fetch_telangana_hc_day(target_date: date) -> "CauseListDay":
    """Adapter so the registry never captures the fetcher by reference.

    The import is deferred to call time so tests can
    ``patch("core.services.cause_list.telangana_hc.fetch_cause_list_day")``
    and have it take effect here.
    """
    from .telangana_hc import fetch_cause_list_day

    return fetch_cause_list_day(target_date)


def _preflight_telangana_hc() -> None:
    """Resolve the bharat_courts Court record for Telangana HC.

    Offline -- a local registry lookup in the library, no network/CAPTCHA.
    Raises CauseListNotConfiguredError if TELANGANA_HC_COURT_KEY is wrong,
    which is exactly what `fetch_cause_lists --check` needs to surface
    before a timer fires against a misconfigured box.
    """
    from .telangana_hc import _court

    _court()


@dataclass(frozen=True)
class CauseListCourt:
    """One court's cause-list wiring.

    key:            stable id; the --court value and the systemd instance
                    name (`case-intel-causelist@<key>.timer`). Lowercase
                    letters/digits/underscore only.
    label:          human name for logs and CLI output.
    fetch_day:      (date) -> CauseListDay. Downloads + parses every
                    document published for that date. Raises
                    CauseListNotPublishedError when the court hasn't put
                    the date up yet (the ordinary evening-before state).
    hearing_filter: ORM kwargs selecting the tracked Hearing rows this
                    court's list can possibly cover (e.g. High Court cases
                    only). Applied on top of the date + status filter in
                    `service.tracked_hearings_on`.
    preflight:      cheap, offline "is this court configured?" check for
                    `fetch_cause_lists --check`. Raises on misconfig.
    """

    key: str
    label: str
    fetch_day: Callable[[date], "CauseListDay"]
    hearing_filter: dict
    preflight: Callable[[], None]

    def __post_init__(self) -> None:
        if not _KEY_RE.match(self.key):
            raise ValueError(
                f"CauseListCourt.key {self.key!r} must match {_KEY_RE.pattern} "
                f"(it is used verbatim as a systemd instance name)."
            )


_ALL_COURTS: dict[str, CauseListCourt] = {}


def _register(court: CauseListCourt) -> None:
    _ALL_COURTS[court.key] = court


_register(
    CauseListCourt(
        key=_TELANGANA_HC_KEY,  # "telangana_hc"
        label=_TELANGANA_HC_LABEL,
        fetch_day=_fetch_telangana_hc_day,
        hearing_filter={"case__tracking_enabled": True, "case__court_type": "high_court"},
        preflight=_preflight_telangana_hc,
    )
)


def get_cause_list_court(key: str) -> CauseListCourt:
    """Look up one registered court, or raise CauseListNotConfiguredError."""
    try:
        return _ALL_COURTS[key]
    except KeyError:
        known = ", ".join(sorted(_ALL_COURTS)) or "(none)"
        raise CauseListNotConfiguredError(
            f"Unknown cause-list court {key!r}. Registered courts: {known}."
        ) from None


def all_registered_courts() -> list[CauseListCourt]:
    return list(_ALL_COURTS.values())


def configured_court_keys() -> list[str]:
    """Court keys the operator has switched on via settings.CAUSE_LIST_COURTS.

    Falls back to just Telangana HC if the setting is unset/empty, so an
    existing deployment keeps working with no .env change.
    """
    keys = [k.strip() for k in getattr(settings, "CAUSE_LIST_COURTS", []) if k.strip()]
    return keys or [_TELANGANA_HC_KEY]


def configured_cause_list_courts() -> list[CauseListCourt]:
    """The CauseListCourt objects for `configured_court_keys()`.

    Raises CauseListNotConfiguredError if the setting names a key with no
    registry entry -- a deploy-time misconfiguration that should fail loud.
    """
    return [get_cause_list_court(key) for key in configured_court_keys()]
