"""The adapter contract and the data classes that cross it.

An adapter owns one *source* (a portal and its way of publishing lists).
It answers four questions and nothing else:

    resolve(case)        which listing target covers this case?   (no network)
    fetch(target, date)  what documents does the court publish?   (network)
    parse(doc)           what matters are in this document?       (pure)
    coverage_for(case)   what do we tell the user about this court?

Everything that decides what a *hearing* is told (listed / not listed /
couldn't check) lives in service.py, not here: an adapter can describe what
it saw, never what that means.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from core.models import Case

# Portals -- the unit the locking and pacing rules are written against.
PORTAL_DISTRICT = "district"
PORTAL_HCSERVICES = "hcservices"
PORTAL_SCI = "sci"


@dataclass(frozen=True)
class ListingTarget:
    """The smallest thing worth fetching, shared by every hearing that maps
    to it (same court, same bench/judge, same date)."""

    adapter: str
    key: str  # stable; grouping + CauseListFetch.target_key
    label: str  # human-readable, for logs and the doctor command
    params: dict = field(default_factory=dict, compare=False, hash=False)


@dataclass(frozen=True)
class Resolution:
    """What `resolve(case)` decided.

    target       a ListingTarget exists; fetch it.
    unsupported  no source covers this case's court -> hearing is "Not
                 covered". `reason` is shown to the advocate.
    pending      the adapter covers this court but cannot yet say where the
                 case sits (e.g. a district case whose court locator is
                 filled by the next refresh). Hearing state is left alone.
    """

    kind: str
    target: ListingTarget | None = None
    reason: str = ""
    adapter: str = ""

    @classmethod
    def for_target(cls, target: ListingTarget) -> "Resolution":
        return cls("target", target=target, adapter=target.adapter)

    @classmethod
    def unsupported(cls, reason: str, adapter: str = "") -> "Resolution":
        return cls("unsupported", reason=reason, adapter=adapter)

    @classmethod
    def pending(cls, reason: str, adapter: str) -> "Resolution":
        return cls("pending", reason=reason, adapter=adapter)

    @property
    def is_target(self) -> bool:
        return self.kind == "target"


@dataclass(frozen=True)
class CauseListEntry:
    """One matter in one list, in the shape every adapter produces."""

    item_number: str
    case_token: str = ""  # as printed ("WP/29408/2026"); "" when only a CNR is printed
    cnr: str = ""  # when the list prints one (district lists always do)
    court_hall: str = ""
    court_name: str = ""
    bench: str = ""
    list_type: str = ""
    stage: str = ""
    connected: tuple[str, ...] = ()  # IA / connected entries: display only, never matched
    is_filing_number: bool = False  # listed by filing no.: never matched
    doc_key: str = ""  # which document it came from (set by the service)


@dataclass
class RawDoc:
    """One document of a fetch: a file on disk plus how it was obtained."""

    doc_key: str
    status: str  # ok | not_uploaded | fetch_error
    path: Path | None = None
    sha256: str = ""
    size: int = 0
    list_type: str = ""
    bench_label: str = ""
    source_ref: str = ""
    source_public: bool = False
    error: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class FetchResult:
    """Everything one fetch learned.

    status       ok | none_available | captcha_failed | fetch_error
    doc_total    how many documents the court's own index lists. Completeness
                 is judged against this, never against len(docs).
    early_exit   the adapter stopped before reading every document because
                 every hearing it was asked about had already been found.
    """

    status: str
    docs: list[RawDoc] = field(default_factory=list)
    doc_total: int = 0
    early_exit: bool = False
    error: str = ""
    note: str = ""


@dataclass
class ParsedDoc:
    entries: list[CauseListEntry]
    list_date: date | None = None
    genuinely_empty: bool = False  # the court said "nothing listed" explicitly


class CauseListAdapter(ABC):
    key: str = ""
    display_name: str = ""
    portal: str = ""
    dormant: bool = False  # built and tested, never routed to

    @abstractmethod
    def resolve(self, case: "Case") -> Resolution:
        """Pure, no network: where would this case's list be?"""

    @abstractmethod
    def fetch(self, target: ListingTarget, list_date: date, workdir: Path) -> FetchResult:
        """Download what the court publishes for `target` on `list_date`
        into `workdir`. Portal states (nothing published, CAPTCHA failure,
        PDF not uploaded) are returned in the result, never raised; only
        bugs raise."""

    @abstractmethod
    def parse(self, doc: RawDoc) -> ParsedDoc:
        """Pure on `doc.path`. Raises CauseListParseError when the document
        is non-empty but yields nothing, or fails the adapter's own
        completeness check -- a silently partial parse reads as 'not
        listed' for whatever it dropped."""

    def finalize_target(self, target: ListingTarget, hearings: list) -> ListingTarget:
        """Last chance to tailor a target to the hearings that share it
        (e.g. which civil/criminal lists to fetch). Pure; default: as is."""
        return target

    def coverage_url(self, case: "Case") -> str:
        """The court's public cause-list page, for the 'verify on the
        court's site' link. Never a session-bound PDF URL."""
        return ""
