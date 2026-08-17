"""
Court tracking service layer: rate limiting, guardrails, and DB sync for
eCourts case data. This is the ONLY place refresh_case_tracking() should
be called from -- views must not call CourtDataProvider directly, so
rate limiting/tracking_enabled checks can't be bypassed.
"""

from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.models import (
    ActivityLog,
    AdvocateProfile,
    Case,
    CourtFetchLog,
    CourtTrackingPreview,
    Hearing,
    ProcessingJob,
)
from core.services.court_data import CaseNotFoundError, CourtCaseData, CourtDataError, get_provider
from core.services.party_role import detect_party_role

logger = logging.getLogger(__name__)

MIN_REFETCH_INTERVAL = timedelta(hours=1)

PREVIEW_TOKEN_TTL = timedelta(minutes=10)
PREVIEW_THROTTLE_MAX = 10
PREVIEW_THROTTLE_WINDOW = timedelta(minutes=10)


class TrackingNotEnabledError(Exception):
    """Raised when refresh_case_tracking() is called for a case with
    tracking_enabled=False."""


class MissingTrackingConfigError(Exception):
    """Raised when tracking_enabled=True but tracking_config is empty."""


class InvalidTrackingConfigError(Exception):
    """Raised when tracking_config carries an unusable court_type.

    Distinct from MissingTrackingConfigError: the config exists, it just
    can't be dispatched. Previously this surfaced as a bare ValueError out
    of the provider, which no caller caught -- a 500 from the refresh
    endpoint and a dead import job. See _resolve_court_type().
    """


class PreviewThrottledError(Exception):
    """Raised when a user exceeds the preview rate limit."""


class PreviewExpiredError(Exception):
    """Raised when a preview_token is unknown, expired, or doesn't belong
    to the requesting user/case."""


class DuplicateCnrError(Exception):
    """Raised when the requesting user already has a case tracking a given
    CNR -- the same-user half of the "Track by CNR" quick-add flow's
    duplicate prevention (see preview_case_creation_from_cnr and
    create_case_from_cnr_preview below). Carries the existing Case so the
    caller can link to it instead of just reporting the conflict."""

    def __init__(self, case: Case):
        self.case = case
        super().__init__(
            f"You already have a case tracking CNR {case.cnr_number} (case {case.case_number!r})."
        )


class CaseNumberConflictError(Exception):
    """Raised when a case_number collides with another owner's case at the
    database level -- the other half of the "Track by CNR" quick-add
    flow's duplicate prevention. case_number is globally unique=True (not
    scoped per owner, see core/models/case.py), a pre-existing schema
    property advocate_import.py already has to handle the same way (see
    its module docstring); create_case_from_cnr_preview mirrors that
    IntegrityError-catch pattern rather than relying on
    CaseCreateSerializer's automatic UniqueValidator, which would
    otherwise intercept the collision earlier with generic DRF wording
    that can't tell this case apart from a same-user CNR duplicate."""

    def __init__(self, case_number: str):
        self.case_number = case_number
        super().__init__(
            f"Case number {case_number!r} is already tracked by another user in the system."
        )


def refresh_case_tracking(case: Case, *, force: bool = False) -> dict:
    """Fetch live court data for `case` and sync it into the DB.

    Guardrails (enforced here, not in views, so nothing can bypass them):
      - Raises TrackingNotEnabledError if case.tracking_enabled is False.
      - Rate-limited to one real fetch per case per hour. Inside that
        window, returns the cached DB state with rate_limited=True
        instead of hitting the portal, UNLESS force=True.

    `force=True` is a raw capability of this function, not an
    authorization check -- callers (views, management commands) are
    responsible for only passing it when the caller is actually allowed
    to bypass the rate limit (staff users / management commands). See
    core/views/case_tracking.py.

    Returns a dict:
        {
            "rate_limited": bool,
            "retry_after": datetime | None,
            "case": Case,
            "data": CourtCaseData | None,   # None when rate_limited
            "new_hearing_dates": list[date],
        }

    Raises CourtDataError (or a subclass) if the fetch itself fails --
    the failure is still logged to CourtFetchLog before re-raising.
    """
    if not case.tracking_enabled:
        raise TrackingNotEnabledError(f"Tracking is not enabled for case {case.id}")

    if not force and case.last_fetched_at is not None:
        elapsed = timezone.now() - case.last_fetched_at
        if elapsed < MIN_REFETCH_INTERVAL:
            return {
                "rate_limited": True,
                "retry_after": case.last_fetched_at + MIN_REFETCH_INTERVAL,
                "case": case,
                "data": None,
                "new_hearing_dates": [],
            }

    if not case.tracking_config:
        raise MissingTrackingConfigError(f"Case {case.id} has no tracking_config set")

    tracking_config = _resolve_court_type(case)

    provider = get_provider()
    start = time.monotonic()
    success = False
    error_message = None
    log_payload = None
    new_hearing_dates: list = []

    try:
        data = provider.fetch_case(tracking_config)
        success = True
        _apply_case_data(case, data)
        new_hearing_dates = _upsert_hearings(case, data)
        log_payload = _build_snapshot(data, new_hearing_dates)
    except CourtDataError as exc:
        error_message = str(exc)
        case.fetch_status = "failed"
        case.save(update_fields=["fetch_status"])
        raise
    except IntegrityError:
        # The (owner, cnr_number) UniqueConstraint added for the "Track by
        # CNR" quick-add flow (see create_case_from_cnr_preview) can fire
        # here too: this case had no CNR yet (_apply_case_data only ever
        # sets it once, on first successful fetch) and the fetch resolved
        # to a CNR that another one of THIS SAME owner's cases already
        # has -- two rows tracking the same real court case. Surface it
        # the same way the quick-add flow does rather than letting a raw
        # IntegrityError become a generic 500 (see CaseTrackingRefreshView).
        success = False
        existing = Case.objects.filter(owner=case.owner, cnr_number=data.cnr).exclude(pk=case.pk).first()
        error_message = f"CNR {data.cnr} is already tracked by another case for this owner."
        case.fetch_status = "failed"
        case.save(update_fields=["fetch_status"])
        if existing is not None:
            raise DuplicateCnrError(existing) from None
        raise
    finally:
        duration_ms = int((time.monotonic() - start) * 1000)
        CourtFetchLog.objects.create(
            owner=case.owner,
            case=case,
            success=success,
            error_message=error_message,
            fields_changed=log_payload,
            duration_ms=duration_ms,
        )

    case.last_fetched_at = timezone.now()
    case.fetch_status = "success"
    case.save(update_fields=["last_fetched_at", "fetch_status"])

    if new_hearing_dates:
        dates_str = ", ".join(d.isoformat() for d in new_hearing_dates)
        ActivityLog.objects.create(
            owner=case.owner,
            case=case,
            activity_type="court_hearing_update",
            description=f"eCourts: new hearing date(s) found for {case.case_number}: {dates_str}",
        )

    _enqueue_order_sync(case)

    return {
        "rate_limited": False,
        "retry_after": None,
        "case": case,
        "data": data,
        "new_hearing_dates": new_hearing_dates,
    }


VALID_COURT_TYPES = ("district", "high_court")


def _resolve_court_type(case: Case) -> dict:
    """Return case.tracking_config with a dispatchable court_type.

    The provider dispatches on tracking_config["court_type"] and raises a
    bare ValueError for anything outside VALID_COURT_TYPES. Nothing caught
    that: the refresh endpoint 500'd and an import job died outright.

    Two behaviours, both deliberate:

      - **Graceful fallback.** If tracking_config's court_type is unusable
        but Case.court_type is valid, use the latter. The two are written
        together everywhere (confirm_case_tracking, advocate_import), so a
        config missing it is a data-shape gap, not a real ambiguity, and
        the case is perfectly refreshable.
      - **No guessing.** If NEITHER is valid we raise rather than defaulting
        to "district". Silently picking a branch would fetch against the
        wrong portal and either fail confusingly or -- much worse -- bind
        the case to a different real case that happens to share the number.
    """
    config = dict(case.tracking_config or {})
    if config.get("court_type") in VALID_COURT_TYPES:
        return config

    if case.court_type in VALID_COURT_TYPES:
        logger.warning(
            "Case %s: tracking_config.court_type=%r is unusable; falling back "
            "to Case.court_type=%r.",
            case.id,
            config.get("court_type"),
            case.court_type,
        )
        config["court_type"] = case.court_type
        return config

    raise InvalidTrackingConfigError(
        f"Case {case.id} has no usable court_type "
        f"(tracking_config={config.get('court_type')!r}, case={case.court_type!r}). "
        f"Re-run court tracking setup for this case."
    )


def _guess_court_type_from_cnr(cnr: str) -> str | None:
    """Best-effort court_type guess from the CNR's own structure.

    Every eCourts CNR encodes a 4-letter prefix identifying the issuing
    court. bharat_courts.infer_court_from_cnr() maps that prefix against a
    table covering all 25 High Courts + the Supreme Court, verified by the
    library against a real eCourts archive sample -- not a guess invented
    here, and no new dependency (bharat-courts is already required).

    A match against a High Court prefix is a strong signal -- return
    "high_court". A match against the Supreme Court prefix ("ESCR") or no
    match at all returns None: this app has no Supreme Court support, and
    more importantly the table has no District Court entries to check
    against (there are thousands of court-complex codes, not a fixed
    enumerable set the way HCs are), so "no match" does NOT confirm
    "district" -- it only means this CNR isn't a currently-known HC/SCI
    prefix. Callers must treat None as "unknown", not "district
    confirmed", and always fall back to the other type on a genuine
    not-found regardless of what this function guessed.
    """
    from bharat_courts import infer_court_from_cnr

    court = infer_court_from_cnr(cnr)
    if court is not None and court.court_type == "high_court":
        return "high_court"
    return None


def _fetch_by_cnr_auto(provider, cnr: str) -> tuple[CourtCaseData, str]:
    """Fetch `cnr` with no known court_type: try whichever portal the
    CNR's own prefix suggests first (see _guess_court_type_from_cnr), then
    the other one -- but ONLY after a genuine CaseNotFoundError from the
    first attempt.

    CaptchaSolveError/CourtPortalError propagate immediately WITHOUT
    falling back to the other portal: those mean "couldn't check", not
    "not there". Falling back on a transient failure would both give a
    misleading answer (a portal outage looks identical to "not filed
    here") and double the CAPTCHA-gated request cost for nothing.

    Returns (data, resolved_court_type) so the caller can persist the
    winning court_type on the case (see confirm_case_tracking) --
    everything after that call resolves court_type off the case directly
    (see _resolve_court_type) and never re-runs this guesswork.

    Raises CaseNotFoundError (with a message naming both portals) if
    neither type has the case. Raises CaptchaSolveError/CourtPortalError
    unchanged if either attempt fails for a reason other than "not found".
    """
    guess = _guess_court_type_from_cnr(cnr)
    if guess:
        other = next(t for t in VALID_COURT_TYPES if t != guess)
        order = (guess, other)
    else:
        order = VALID_COURT_TYPES

    try:
        return provider.fetch_case_by_cnr(cnr, order[0]), order[0]
    except CaseNotFoundError:
        pass  # genuine not-found on the first portal -- try the other one

    try:
        return provider.fetch_case_by_cnr(cnr, order[1]), order[1]
    except CaseNotFoundError:
        raise CaseNotFoundError(
            f"No case found with CNR {cnr!r} in either District Court or "
            "High Court records."
        ) from None


def _enqueue_order_sync(case: Case) -> None:
    """Queue the Phase B order-sync step after a successful hearing sync.

    Runs in the process_jobs worker, never inline -- the portal-facing
    downloads (sequential, delayed) must not sit inside a request cycle.
    Only reachable from refresh_case_tracking/confirm_case_tracking, both
    of which sit behind the per-case refresh cooldown, so order sync
    inherits that rate limit; ProcessingJob.enqueue_order_sync also
    dedupes against an already-queued/running sync for the same case.
    Never raises -- an enqueue failure must not fail the fetch that
    triggered it.
    """
    try:
        ProcessingJob.enqueue_order_sync(case)
    except Exception:
        logger.warning("Failed to enqueue order sync for case %s", case.id, exc_info=True)


def _cleanup_expired_previews() -> None:
    """Delete preview rows that expired without ever being confirmed.

    Confirmed rows are deleted immediately in confirm_case_tracking(), so
    this only ever catches abandoned ones. No Celery/cron needed -- this
    table sees setup-flow volume only (a handful of rows per user per
    session), so a cheap indexed DELETE on every preview call is enough to
    keep it from growing unbounded. Safe to call from any worker process;
    unlike the old LocMemCache TTL, expiry here is a real column every
    worker can see and delete against.
    """
    CourtTrackingPreview.objects.filter(expires_at__lte=timezone.now()).delete()


def _check_preview_throttle(user_id: int) -> None:
    """Max PREVIEW_THROTTLE_MAX previews per user per PREVIEW_THROTTLE_WINDOW.

    Preview is exempt from the per-case 1h rate limit (nothing is
    persisted), so without this a preview loop would be an unlimited free
    live-fetch endpoint. Counts CourtTrackingPreview rows created in the
    trailing window rather than an incrementing cache counter -- a real
    table row every worker process can see and count identically, unlike
    the old per-process LocMemCache counter (which under-enforced the
    limit by up to Nx on an N-worker deployment, since each worker kept its
    own separate count).

    Note: confirm_case_tracking() deletes a row as soon as it's confirmed,
    so a preview that's confirmed quickly stops counting toward this
    window immediately -- this module has always favored a simple,
    slightly-racy check over exact enforcement (see the original
    MIN_REFETCH_INTERVAL check, which doesn't lock either), and that trade
    still holds here.
    """
    window_start = timezone.now() - PREVIEW_THROTTLE_WINDOW
    count = CourtTrackingPreview.objects.filter(
        user_id=user_id, created_at__gte=window_start
    ).count()
    if count >= PREVIEW_THROTTLE_MAX:
        raise PreviewThrottledError(
            f"Too many preview attempts ({PREVIEW_THROTTLE_MAX} per "
            f"{int(PREVIEW_THROTTLE_WINDOW.total_seconds() // 60)} minutes). Please wait and try again."
        )


def preview_case_tracking(case: Case, tracking_config: dict, *, user_id: int) -> dict:
    """Fetch live court data WITHOUT persisting anything to the case.

    This is the fix for tracking silently saving a mismatched case: setup
    used to fetch-and-persist in one step, so a wrong case_type/case_number
    combination that happened to resolve to a DIFFERENT real case saved
    that wrong case's data with no human check. Preview separates "fetch"
    from "save" -- the caller must show the result to a human and call
    confirm_case_tracking() with the returned preview_token to persist it.

    tracking_config accepts either shape CourtDataProvider.fetch_case()
    understands: the cascade shape (state/dist/complex/case_type/
    case_number/year, or the HC equivalent, court_type required), or the
    CNR-first shape ({"cnr": "...", "court_type": ...}) -- court_type is
    OPTIONAL in the CNR-first shape: when omitted (or not a valid value),
    it's auto-detected from the CNR itself (see _fetch_by_cnr_auto), which
    tries the portal the CNR's own prefix suggests first and falls back to
    the other one on a genuine not-found. An explicit court_type alongside
    cnr is still honored as-is (no detection, no fallback) for callers
    that already know it.

    The preview token is stored in CourtTrackingPreview (Postgres), not
    Django's cache -- it has to be visible to whichever gunicorn worker
    handles the later confirm_case_tracking() call, and LocMemCache is
    per-process.

    Raises PreviewThrottledError if the per-user throttle is exceeded.
    Raises CourtDataError (or a subclass) if the fetch itself fails --
    nothing is persisted in that case.
    """
    _cleanup_expired_previews()
    _check_preview_throttle(user_id)

    provider = get_provider()

    cnr = tracking_config.get("cnr")
    court_type_detected = False
    if cnr and tracking_config.get("court_type") not in VALID_COURT_TYPES:
        data, resolved_court_type = _fetch_by_cnr_auto(provider, cnr)
        tracking_config = {**tracking_config, "court_type": resolved_court_type}
        court_type_detected = True
    else:
        data = provider.fetch_case(tracking_config)

    token = secrets.token_urlsafe(24)
    CourtTrackingPreview.objects.create(
        token=token,
        case=case,
        user_id=user_id,
        payload={
            "tracking_config": dict(tracking_config),
            "data": data.to_dict(),
        },
        expires_at=timezone.now() + PREVIEW_TOKEN_TTL,
    )

    case_title = " vs ".join(p for p in (data.petitioner, data.respondent) if p) or None

    return {
        "preview_token": token,
        "case_title": case_title,
        "cnr": data.cnr,
        "petitioner": data.petitioner,
        "respondent": data.respondent,
        "court_name": data.court_name,
        "case_status": data.case_status,
        "case_stage": data.case_stage,
        "court_type": tracking_config.get("court_type"),
        "court_type_detected": court_type_detected,
        "case_type": tracking_config.get("case_type"),
        "case_number": tracking_config.get("case_number"),
        "year": tracking_config.get("year"),
        "next_hearing_date": data.next_hearing_date.isoformat() if data.next_hearing_date else None,
        "first_hearing_date": data.first_hearing_date.isoformat() if data.first_hearing_date else None,
        "hearing_count": len(data.hearing_history),
    }


def confirm_case_tracking(case: Case, preview_token: str, *, user_id: int) -> dict:
    """Persist a previously-previewed fetch.

    Never trusts client-supplied case data -- loads ONLY the server-side
    payload keyed by preview_token (and checks it actually belongs to this
    case and this user) rather than anything in the request body, so a
    confirm call can't be used to smuggle in different data than what was
    actually previewed and shown to the user. The payload comes from
    CourtTrackingPreview (Postgres), not Django's cache -- readable from
    whichever gunicorn worker handles this request, regardless of which
    worker handled the earlier preview call.

    Raises PreviewExpiredError if the token is unknown, expired, or
    doesn't match this case/user -- the caller should tell the user to
    preview again rather than silently retrying.
    """
    try:
        preview = CourtTrackingPreview.objects.get(token=preview_token)
    except CourtTrackingPreview.DoesNotExist:
        raise PreviewExpiredError("This preview has expired. Please search again.")

    if preview.expires_at <= timezone.now():
        preview.delete()
        raise PreviewExpiredError("This preview has expired. Please search again.")

    if preview.case_id != case.id or preview.user_id != user_id:
        raise PreviewExpiredError("This preview does not match the requested case. Please search again.")

    data: CourtCaseData = CourtCaseData.from_dict(preview.payload["data"])
    tracking_config: dict = preview.payload["tracking_config"]

    case.court_type = tracking_config.get("court_type")
    case.tracking_config = tracking_config
    case.tracking_enabled = True
    case.save(update_fields=["court_type", "tracking_config", "tracking_enabled"])

    new_hearing_dates = _finalize_confirmed_fetch(case, data)

    # One-time use -- a stale token can't be replayed to re-persist the
    # same (or since-changed) payload after this.
    preview.delete()

    return {"case": case, "data": data, "new_hearing_dates": new_hearing_dates}


def _finalize_confirmed_fetch(case: Case, data: CourtCaseData) -> list:
    """Apply a confirmed fetch onto a case that already has
    court_type/tracking_config/tracking_enabled set: CNR/party-advocate
    fields, hearing upsert, fetch log, last_fetched_at/fetch_status, an
    ActivityLog entry for new hearings, and order-sync enqueue.

    Shared by confirm_case_tracking() (an existing case being tracked for
    the first time) and create_case_from_cnr_preview() (a brand-new case
    created directly from a case-less CNR preview, see below) so both end
    up in byte-identical post-fetch state. Returns new_hearing_dates.
    """
    _apply_case_data(case, data)
    new_hearing_dates = _upsert_hearings(case, data)
    log_payload = _build_snapshot(data, new_hearing_dates)

    CourtFetchLog.objects.create(
        owner=case.owner,
        case=case,
        success=True,
        error_message=None,
        fields_changed=log_payload,
        duration_ms=None,
    )

    case.last_fetched_at = timezone.now()
    case.fetch_status = "success"
    case.save(update_fields=["last_fetched_at", "fetch_status"])

    if new_hearing_dates:
        dates_str = ", ".join(d.isoformat() for d in new_hearing_dates)
        ActivityLog.objects.create(
            owner=case.owner,
            case=case,
            activity_type="court_hearing_update",
            description=f"eCourts: new hearing date(s) found for {case.case_number}: {dates_str}",
        )

    _enqueue_order_sync(case)
    return new_hearing_dates


def preview_case_creation_from_cnr(cnr: str, court_type: str | None, *, user) -> dict:
    """Case-less variant of preview_case_tracking() for the "Track by CNR"
    quick-add flow on the manual case entry page (see
    core/views/case_tracking.py's CaseCnrLookupView) -- fetches a CNR
    before any Case row exists yet, so the advocate can review/edit the
    result before anything is created.

    Reuses the exact same fetch machinery as the per-case preview
    (_fetch_by_cnr_auto/get_provider) and the same party-role detection
    advocate_import.py uses (detect_party_role), just sourced from the
    requesting user's own AdvocateProfile instead of a searched advocate
    identity -- a direct CNR entry has no "searched advocate" to compare
    against. Degrades to "unknown" cleanly (same as advocate_import) when
    the user has no AdvocateProfile yet, or its letterhead_name is blank.

    case_number in the returned preview uses the fetched
    registration_number (the portal's own case number, e.g.
    "WP/23998/2026") when eCourts provides one -- that's what the cause-
    list matcher and every other case_number consumer in this app expect
    to see, not the CNR. Only falls back to the CNR itself, matching
    advocate_import.py's convention, for the rare record types whose
    case-history page has no Registration Number row at all. title uses
    "Petitioner vs Respondent" (same join convention as
    preview_case_tracking's case_title), falling back to case_number only
    when eCourts returns neither party name. The caller can still edit
    either before confirming.

    Raises DuplicateCnrError immediately, before touching the portal, if
    the requesting user already has a case tracking this CNR -- a known
    duplicate should never cost a CAPTCHA-gated fetch.
    Raises PreviewThrottledError if the per-user preview throttle is
    exceeded (shared with the per-case preview flow -- same table, same
    counter, so this can't be used to bypass it as a separate free-fetch
    endpoint).
    Raises CourtDataError (or a subclass) if the fetch itself fails --
    nothing is persisted in that case.
    """
    existing = Case.objects.filter(owner=user, cnr_number=cnr).first()
    if existing is not None:
        raise DuplicateCnrError(existing)

    _cleanup_expired_previews()
    _check_preview_throttle(user.id)

    provider = get_provider()

    court_type_detected = False
    if court_type in VALID_COURT_TYPES:
        data = provider.fetch_case_by_cnr(cnr, court_type)
        resolved_court_type = court_type
    else:
        data, resolved_court_type = _fetch_by_cnr_auto(provider, cnr)
        court_type_detected = True

    tracking_config = {"cnr": cnr, "court_type": resolved_court_type}

    advocate_profile = AdvocateProfile.objects.filter(owner=user).first()
    user_party_role = "unknown"
    if advocate_profile is not None:
        user_party_role = detect_party_role(
            advocate_profile.letterhead_name,
            advocate_profile.bar_registration_number,
            data.party_advocate_data,
        )

    opposing_party = None
    if user_party_role == "petitioner":
        opposing_party = data.respondent or None
    elif user_party_role == "respondent":
        opposing_party = data.petitioner or None

    # The portal's own case number, not the CNR -- see
    # CourtCaseData.registration_number's docstring. Only a handful of
    # record types come back with no Registration Number row at all, and
    # that's the only case the CNR fallback should ever cover.
    case_number = data.registration_number or cnr

    # "Petitioner vs Respondent" is a human-recognizable case title;
    # case_number/CNR are not. Same join convention preview_case_tracking
    # already uses for its case_title field (joins whichever of the two
    # names came back, so one-sided data still produces something rather
    # than a lopsided "Name vs "), just falling back to case_number
    # instead of None here, since this title is what gets pre-filled into
    # the quick-add form, not a display-only preview value.
    case_title = " vs ".join(p for p in (data.petitioner, data.respondent) if p) or case_number

    token = secrets.token_urlsafe(24)
    CourtTrackingPreview.objects.create(
        token=token,
        case=None,
        user_id=user.id,
        payload={"tracking_config": dict(tracking_config), "data": data.to_dict()},
        expires_at=timezone.now() + PREVIEW_TOKEN_TTL,
    )

    return {
        "preview_token": token,
        "cnr": data.cnr,
        "case_number": case_number,
        "title": case_title,
        "user_party_role": user_party_role,
        "opposing_party": opposing_party,
        "petitioner": data.petitioner,
        "respondent": data.respondent,
        "court_name": data.court_name,
        "case_status": data.case_status,
        "case_stage": data.case_stage,
        "court_type": resolved_court_type,
        "court_type_detected": court_type_detected,
        "next_hearing_date": data.next_hearing_date.isoformat() if data.next_hearing_date else None,
        "first_hearing_date": data.first_hearing_date.isoformat() if data.first_hearing_date else None,
        "hearing_count": len(data.hearing_history),
    }


def create_case_from_cnr_preview(preview_token: str, case_fields: dict, *, user) -> Case:
    """Persists a case-less CNR preview (preview_case_creation_from_cnr)
    into a brand-new Case with tracking already configured -- the confirm
    step of the "Track by CNR" quick-add flow. Never trusts client-supplied
    court data: loads ONLY the server-cached payload keyed by
    preview_token, the same principle confirm_case_tracking() follows.

    case_fields is the validated field set from CaseCnrCreateSerializer
    (case_number, title, client_name, opposing_party, user_party_role,
    case_type, status, priority, filing_date, notes) -- whatever the
    advocate reviewed/edited in the pre-filled form.

    Raises PreviewExpiredError if the token is unknown, expired, or
    doesn't belong to this user -- including a per-case preview token from
    the OTHER (CaseTrackingPreviewView) flow, since preview.case_id will
    never be None there.
    Raises DuplicateCnrError if the user already has a case tracking this
    CNR (re-checked here to close the race with a second request between
    preview and confirm; the DB-level UniqueConstraint on
    (owner, cnr_number) is the final backstop for the same race).
    Raises CaseNumberConflictError if case_number collides with another
    owner's case at the database level.
    """
    try:
        preview = CourtTrackingPreview.objects.get(token=preview_token)
    except CourtTrackingPreview.DoesNotExist:
        raise PreviewExpiredError("This preview has expired. Please fetch the CNR again.")

    if preview.expires_at <= timezone.now():
        preview.delete()
        raise PreviewExpiredError("This preview has expired. Please fetch the CNR again.")

    if preview.case_id is not None or preview.user_id != user.id:
        raise PreviewExpiredError("This preview does not match. Please fetch the CNR again.")

    data: CourtCaseData = CourtCaseData.from_dict(preview.payload["data"])
    tracking_config: dict = preview.payload["tracking_config"]
    cnr = tracking_config["cnr"]

    existing = Case.objects.filter(owner=user, cnr_number=cnr).first()
    if existing is not None:
        raise DuplicateCnrError(existing)

    try:
        with transaction.atomic():
            case = Case.objects.create(
                owner=user,
                court_type=tracking_config.get("court_type"),
                tracking_config=tracking_config,
                tracking_enabled=True,
                **case_fields,
            )
    except IntegrityError:
        # Disambiguate which of the two possible collisions fired: the new
        # (owner, cnr_number) constraint (a genuine race with another
        # request since the check above -- same-user duplicate) or the
        # pre-existing global case_number uniqueness (another owner's
        # case). Mirrors advocate_import.py's own two-distinct-outcomes
        # handling for the identical ambiguity.
        existing = Case.objects.filter(owner=user, cnr_number=cnr).first()
        if existing is not None:
            raise DuplicateCnrError(existing) from None
        raise CaseNumberConflictError(case_fields["case_number"]) from None

    _finalize_confirmed_fetch(case, data)
    preview.delete()
    return case


def untrack_case(case: Case) -> None:
    """Clear all court-tracking state for a case: the setup-mismatch
    recovery path (Part 3).

    Clears last_fetched_at along with everything else -- leaving it set
    would let the wrong case's fetch continue rate-limiting a correct
    re-track attempt for up to an hour, which is exactly the recovery
    flow this function exists for. Only Hearing rows with source='ecourts'
    are deleted; manually-entered hearings are untouched.
    """
    Hearing.objects.filter(case=case, source="ecourts").delete()

    case.cnr_number = None
    case.court_type = None
    case.tracking_config = None
    case.tracking_enabled = False
    case.fetch_status = "never_fetched"
    case.last_fetched_at = None
    case.save(
        update_fields=[
            "cnr_number",
            "court_type",
            "tracking_config",
            "tracking_enabled",
            "fetch_status",
            "last_fetched_at",
        ]
    )

    ActivityLog.objects.create(
        owner=case.owner,
        case=case,
        activity_type="court_tracking_removed",
        description=f"Court tracking removed for {case.case_number}",
    )


def _apply_case_data(case: Case, data: CourtCaseData) -> None:
    """Persist the CNR on first successful fetch. Everything else
    (status/stage/judge/next hearing) is derived from Hearing rows and
    the latest CourtFetchLog snapshot -- see _build_snapshot -- rather
    than new Case columns, since Phase A1 deliberately didn't add them.

    party_advocate_data is the exception -- it's raw per-party advocate
    names captured for party-role detection, not a display snapshot, so
    it's kept current on every successful fetch (not just the first)."""
    update_fields = []
    if not case.cnr_number and data.cnr:
        case.cnr_number = data.cnr
        update_fields.append("cnr_number")
    if data.party_advocate_data and case.party_advocate_data != data.party_advocate_data:
        case.party_advocate_data = data.party_advocate_data
        update_fields.append("party_advocate_data")
    if update_fields:
        case.save(update_fields=update_fields)


def _upsert_hearings(case: Case, data: CourtCaseData) -> list:
    """Upsert Hearing rows for source='ecourts', deduped on
    (case, hearing_date, source) per the unique constraint. Returns the
    list of hearing dates that are genuinely new (didn't exist before
    this call) -- the signal an ActivityLog entry gets written for.

    `location` is stamped from data.court_name (case-level -- the
    provider's hearing-history table has no per-row court/location
    column, only hearing_date/business_date/purpose/judge/
    cause_list_type, see HearingRecord) on every hearing for this case,
    same as judge/purpose below."""
    new_dates = []
    today = timezone.localdate()

    for record in data.hearing_history:
        if record.hearing_date is None:
            continue

        hearing_datetime = timezone.make_aware(
            datetime.combine(record.hearing_date, datetime.min.time())
        )
        existed = Hearing.objects.filter(
            case=case, hearing_date=hearing_datetime, source="ecourts"
        ).exists()

        Hearing.objects.update_or_create(
            case=case,
            hearing_date=hearing_datetime,
            source="ecourts",
            defaults={
                "owner": case.owner,
                "hearing_type": "other",
                "location": data.court_name or "",
                "judge": record.judge or "",
                "business_date": record.business_date,
                "purpose": record.purpose or "",
                "status": "completed" if record.hearing_date < today else "scheduled",
            },
        )

        if not existed:
            new_dates.append(record.hearing_date)

    return new_dates


def _build_snapshot(data: CourtCaseData, new_hearing_dates: list) -> dict:
    """CourtFetchLog.fields_changed payload: a full snapshot of what the
    fetch returned (so the API layer has a persistent place to read
    current status/stage/judge from without new Case columns) plus an
    explicit list of which fields were new this run, for at-a-glance
    debugging."""
    return {
        "snapshot": {
            "cnr": data.cnr,
            "case_status": data.case_status,
            "case_stage": data.case_stage,
            "court_and_judge": data.court_and_judge,
            "court_name": data.court_name,
            "next_hearing_date": data.next_hearing_date.isoformat() if data.next_hearing_date else None,
            "first_hearing_date": data.first_hearing_date.isoformat() if data.first_hearing_date else None,
            "nature_of_disposal": data.nature_of_disposal,
            "hearing_count": len(data.hearing_history),
        },
        "new_hearing_dates": [d.isoformat() for d in new_hearing_dates],
    }


def latest_snapshot(case: Case) -> dict | None:
    """The snapshot from the most recent successful fetch, for display
    without triggering a new one. None if the case has never been
    fetched successfully."""
    log = (
        CourtFetchLog.objects.filter(case=case, success=True)
        .order_by("-timestamp")
        .first()
    )
    if log is None or not log.fields_changed:
        return None
    return log.fields_changed.get("snapshot")


# Recent-hearing rows included in the AI context block. Kept small on
# purpose -- the block must stay a few hundred tokens, not the full
# hearing history (which can run to dozens of rows on an old case).
AI_CONTEXT_MAX_HEARINGS = 5

_AI_CONTEXT_DATE_FORMAT = "%d %b %Y"


def build_ai_context(case: Case) -> dict | None:
    """Compact court-tracking context for the Case Bot generation prompt.

    Returns None unless the case has tracking enabled AND at least one
    successful fetch (a snapshot to report) -- an untracked case must
    leave the chat pipeline exactly as it was.

    Returns:
        {
            "block": str,         # the data block injected into the prompt
            "source_label": str,  # e.g. "eCourts tracking data (refreshed 19 Jul 2026, 17:06 UTC)"
        }

    This is prompt context from LIVE PORTAL DATA, not from any uploaded
    document -- the caller must present it to the LLM as a separate block
    from retrieved chunks so answers never attribute these facts to a
    document citation.
    """
    if not case.tracking_enabled:
        return None
    snapshot = latest_snapshot(case)
    if snapshot is None:
        return None

    if case.last_fetched_at:
        local = timezone.localtime(case.last_fetched_at)
        refreshed = local.strftime(f"{_AI_CONTEXT_DATE_FORMAT}, %H:%M %Z")
    else:
        refreshed = "unknown"

    def _fmt_date(iso: str | None) -> str | None:
        if not iso:
            return None
        try:
            return datetime.fromisoformat(iso).strftime(_AI_CONTEXT_DATE_FORMAT)
        except ValueError:
            return iso

    lines = []
    if snapshot.get("case_status"):
        lines.append(f"Case status: {snapshot['case_status']}")
    if snapshot.get("case_stage"):
        lines.append(f"Case stage: {snapshot['case_stage']}")
    if snapshot.get("court_name"):
        lines.append(f"Court: {snapshot['court_name']}")
    if snapshot.get("court_and_judge"):
        lines.append(f"Court number and judge: {snapshot['court_and_judge']}")
    if case.cnr_number:
        lines.append(f"CNR number: {case.cnr_number}")
    next_date = _fmt_date(snapshot.get("next_hearing_date"))
    if next_date:
        lines.append(f"Next hearing date: {next_date}")
    first_date = _fmt_date(snapshot.get("first_hearing_date"))
    if first_date:
        lines.append(f"First hearing date: {first_date}")
    if snapshot.get("nature_of_disposal"):
        lines.append(f"Nature of disposal: {snapshot['nature_of_disposal']}")

    recent = (
        Hearing.objects.filter(case=case, source="ecourts")
        .order_by("-hearing_date")[:AI_CONTEXT_MAX_HEARINGS]
    )
    hearing_lines = []
    for h in recent:
        parts = [h.hearing_date.strftime(_AI_CONTEXT_DATE_FORMAT)]
        if h.purpose:
            parts.append(h.purpose)
        parts.append(f"({h.status})")
        hearing_lines.append("- " + " — ".join(parts[:-1]) + f" {parts[-1]}")
    if hearing_lines:
        lines.append(f"Most recent hearings (up to {AI_CONTEXT_MAX_HEARINGS}):")
        lines.extend(hearing_lines)

    if not lines:
        return None

    return {
        "block": "\n".join(lines),
        "source_label": f"eCourts tracking data (refreshed {refreshed})",
    }
