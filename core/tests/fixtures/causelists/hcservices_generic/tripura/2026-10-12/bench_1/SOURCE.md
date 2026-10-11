# SOURCE - hcservices tripura (bench 1) list date 2026-10-12

Fetched live from the eCourts HC Services portal on 2026-10-10 (IST), around 20:49.

**Meta-table request** (CAPTCHA solved by bharat-courts' ddddocr solver, new session per attempt):

    POST https://hcservices.ecourts.gov.in/hcservices/cases_qry/index_qry.php
    action_code=showCauseList  flag=civ_t  selprevdays=0
    state_code=20  court_code=1  caseStatusSearchType=CLcauselist
    causelist_date=12-10-2026  captcha=<solved>
    Referer: https://hcservices.ecourts.gov.in/hcservices/main.php

- `00_meta_table.html` - the raw response (table.causelistTbl). 2 index rows.
- PDF actually downloaded: `DAILY_MAIN_CAUSE_LIST_HON_BLE_JUSTICE_DR_T_AMARNATH_GOUD.pdf`  (list type: DAILY MAIN CAUSE LIST; bench label: HON'BLE JUSTICE DR. T. AMARNATH GOUD)
- PDF URL: https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=Phus9qDUtAITMaFhGVK30TIQC3vjjqck5hBlWqe4MHM%3D&causelistYear=2026
- PDF present on the portal: yes
- PDF fetched at: 2026-10-10T20:49:54.654880+05:30
- Saved verbatim after cutting any bytes before the `%PDF` header (the portal prepends a UTF-8 BOM).

- **Trimmed fixture:** `DAILY_MAIN_CAUSE_LIST_HON_BLE_JUSTICE_DR_T_AMARNATH_GOUD.pdf` is pages 1-2 of 4 of the original PDF (original 181,093 bytes, sha256 `49a0adb58862e15abdffe4b7708a4560964cb3a2384d475fb06447f1041bfbfa`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.
