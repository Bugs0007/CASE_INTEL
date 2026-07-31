"""Cause-list failure modes, kept distinct because they mean very
different things operationally."""


class CauseListError(Exception):
    """Base for every cause-list failure."""


class CauseListNotConfiguredError(CauseListError):
    """The cause-list source URL isn't set (see
    TELANGANA_HC_CAUSE_LIST_URL in settings.py).

    An operator problem, not a court problem -- the fetch never left the
    building, so nothing should be recorded as "not published".
    """


class CauseListNotPublishedError(CauseListError):
    """The court hasn't put this date's list up yet.

    The NORMAL state the evening before a hearing, not an error to alert
    on: the run records "not yet listed" and tries again on the next
    scheduled pass.
    """


class CauseListParseError(CauseListError):
    """A document was fetched but doesn't look like this court's cause
    list.

    Worth alerting on -- it usually means the portal changed its layout
    and the parser needs updating, which would otherwise show up as every
    case silently going "not listed".
    """
