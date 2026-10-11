# SOURCE - hcservices jammu (bench 1) list date 2026-10-12

Fetched live from the eCourts HC Services portal on 2026-10-10 (IST), around 20:48.

**Meta-table request** (CAPTCHA solved by bharat-courts' ddddocr solver, new session per attempt):

    POST https://hcservices.ecourts.gov.in/hcservices/cases_qry/index_qry.php
    action_code=showCauseList  flag=civ_t  selprevdays=0
    state_code=12  court_code=1  caseStatusSearchType=CLcauselist
    causelist_date=12-10-2026  captcha=<solved>
    Referer: https://hcservices.ecourts.gov.in/hcservices/main.php

- `00_meta_table.html` - the raw response (table.causelistTbl). 23 index rows.
- PDF actually downloaded: `Regular_HON_BLE_THE_CHIEF_JUSTICE_HON_BLE_MR_JUSTICE_RAJESH_SEKHRI.pdf`  (list type: Regular; bench label: HON'BLE THE CHIEF JUSTICE, HON'BLE MR.  JUSTICE RAJESH SEKHRI)
- PDF URL: https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=%2BNUCuT5LC9PuPNJB%2B%2Bw1NFlqI7SCR3Soj%2F0vQ9GnjFI%3D&causelistYear=2026
- PDF present on the portal: yes
- PDF fetched at: 2026-10-10T20:48:34.355148+05:30
- Saved verbatim after cutting any bytes before the `%PDF` header (the portal prepends a UTF-8 BOM).

- **Trimmed fixture:** `Regular_HON_BLE_THE_CHIEF_JUSTICE_HON_BLE_MR_JUSTICE_RAJESH_SEKHRI.pdf` is pages 1-1 of 1 of the original PDF (original 29,599 bytes, sha256 `743068567281d4a8d140d898ea5f5c8ba21f0d80f8c99fd6b5de7e02f7dd472c`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.
