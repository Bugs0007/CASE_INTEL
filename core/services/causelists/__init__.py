"""Cause-list ingestion for every court Case Intel can tell an advocate
about: item number, court, bench and list type for each tracked hearing.

Layout (see docs/causelists/PLAN.md for the reasoning):

    base.py       adapter contract and the data classes that cross it
    registry.py   Case -> adapter/target (or "not covered"); no network
    normalize.py  canonical case keys, alias tables as data
    matcher.py    entries <-> hearings (CNR first, then case key)
    fetchlib.py   response classification, pacing, streamed downloads
    lock.py       advisory lock + per-portal "is a heavy job running" checks
    service.py    the ONLY writer of Hearing.cause_list_*; owns the
                  state machine that decides `not_listed`
    adapters/     one module per source (telangana_hc, district_ecourts,
                  hcservices_generic, supreme_court)

The one rule everything here serves: absence is only evidence when the
whole published list was read. See `service.apply_group`.
"""
