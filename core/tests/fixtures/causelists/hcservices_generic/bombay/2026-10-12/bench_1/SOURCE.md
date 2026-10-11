# SOURCE - hcservices bombay (bench 1) list date 2026-10-12

Fetched live from the eCourts HC Services portal on 2026-10-10 (IST), around 20:47.

**Meta-table request** (CAPTCHA solved by bharat-courts' ddddocr solver, new session per attempt):

    POST https://hcservices.ecourts.gov.in/hcservices/cases_qry/index_qry.php
    action_code=showCauseList  flag=civ_t  selprevdays=0
    state_code=1  court_code=1  caseStatusSearchType=CLcauselist
    causelist_date=12-10-2026  captcha=<solved>
    Referer: https://hcservices.ecourts.gov.in/hcservices/main.php

- `00_meta_table.html` - the raw response (table.causelistTbl). 48 index rows.
- PDF actually downloaded: `Daily_Main_HON_BLE_THE_CHIEF_JUSTICE_HON_BLE_JUSTICE_ADVAIT_M_SETHNA.pdf`  (list type: Daily Main; bench label: HON'BLE THE CHIEF JUSTICE, HON'BLE JUSTICE ADVAIT M. SETHNA)
- PDF URL: https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=GfnClQc4qSlL2oz60F4UK7UXxaqI6kNyL99ztfYCGYo%3D&causelistYear=2026
- PDF present on the portal: yes
- PDF fetched at: 2026-10-10T20:47:47.341249+05:30
- Saved verbatim after cutting any bytes before the `%PDF` header (the portal prepends a UTF-8 BOM).

- **Trimmed fixture:** `Daily_Main_HON_BLE_THE_CHIEF_JUSTICE_HON_BLE_JUSTICE_ADVAIT_M_SETHNA.pdf` is pages 1-2 of 18 of the original PDF (original 94,408 bytes, sha256 `b6713f48a262009293b503448551774a099f7b351d54d203d7aa880401aace87`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.
