# SOURCE - hcservices bombay (bench 1) list date 2026-10-09

Fetched live from the eCourts HC Services portal on 2026-10-10 (IST), around 20:34.

**Meta-table request** (CAPTCHA solved by bharat-courts' ddddocr solver, new session per attempt):

    POST https://hcservices.ecourts.gov.in/hcservices/cases_qry/index_qry.php
    action_code=showCauseList  flag=civ_t  selprevdays=1
    state_code=1  court_code=1  caseStatusSearchType=CLcauselist
    causelist_date=09-10-2026  captcha=<solved>
    Referer: https://hcservices.ecourts.gov.in/hcservices/main.php

- `00_meta_table.html` - the raw response (table.causelistTbl). 65 index rows.
- PDF actually downloaded: `Daily_Main__HON_BLE_THE_CHIEF_JUSTICE__HON_BLE_JUSTICE_ADVAIT_M__SETHNA.pdf`  (list type: Daily Main; bench label: HON'BLE THE CHIEF JUSTICE, HON'BLE JUSTICE ADVAIT M. SETHNA)
- PDF URL: https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=d036EIoKihVm9IThJaNGjtBgWu0InxkyHwaDVVAS9VU%3D&causelistYear=2026
- PDF present on the portal: yes
- PDF fetched at: 2026-10-10T20:34:39+05:30
- Saved verbatim after cutting any bytes before the `%PDF` header (the portal prepends a UTF-8 BOM).

- **Trimmed fixture:** `Daily_Main__HON_BLE_THE_CHIEF_JUSTICE__HON_BLE_JUSTICE_ADVAIT_M__SETHNA.pdf` is pages 1-2 of 15 of the original PDF (original 86,416 bytes, sha256 `b2d37a2048f329fe26c149a7200ec7f6bc6f0a15048e220eea82217792dde021`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.
