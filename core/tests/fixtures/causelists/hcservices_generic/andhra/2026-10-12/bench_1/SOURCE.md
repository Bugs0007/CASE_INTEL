# SOURCE - hcservices andhra (bench 1) list date 2026-10-12

Fetched live from the eCourts HC Services portal on 2026-10-10 (IST), around 20:33.

**Meta-table request** (CAPTCHA solved by bharat-courts' ddddocr solver, new session per attempt):

    POST https://hcservices.ecourts.gov.in/hcservices/cases_qry/index_qry.php
    action_code=showCauseList  flag=civ_t  selprevdays=0
    state_code=2  court_code=1  caseStatusSearchType=CLcauselist
    causelist_date=12-10-2026  captcha=<solved>
    Referer: https://hcservices.ecourts.gov.in/hcservices/main.php

- `00_meta_table.html` - the raw response (table.causelistTbl). 41 index rows.
- PDF actually downloaded: `FRESH_MOTION_HEARING__LISA_GILL__CHALLA_GUNARANJAN.pdf`  (list type: FRESH MOTION HEARING; bench label: LISA GILL, CHALLA GUNARANJAN)
- PDF URL: https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=jr8gzDB6c5AI8W7MGf3NYU7rT7AUPR%2FIxWl3LeLCrIU%3D&causelistYear=2026
- PDF present on the portal: yes
- PDF fetched at: 2026-10-10T20:33:49+05:30
- Saved verbatim after cutting any bytes before the `%PDF` header (the portal prepends a UTF-8 BOM).

- **Trimmed fixture:** `FRESH_MOTION_HEARING__LISA_GILL__CHALLA_GUNARANJAN.pdf` is pages 1-2 of 3 of the original PDF (original 67,478 bytes, sha256 `1a125fde7ff3521b0445f4a32fe18797bae989d62a11e5a4b3cfe5c14747272c`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.
