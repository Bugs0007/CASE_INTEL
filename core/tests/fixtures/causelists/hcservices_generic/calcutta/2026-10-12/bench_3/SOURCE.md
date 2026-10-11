# SOURCE - hcservices calcutta (bench 3) list date 2026-10-12

Fetched live from the eCourts HC Services portal on 2026-10-10 (IST), around 20:47.

**Meta-table request** (CAPTCHA solved by bharat-courts' ddddocr solver, new session per attempt):

    POST https://hcservices.ecourts.gov.in/hcservices/cases_qry/index_qry.php
    action_code=showCauseList  flag=civ_t  selprevdays=0
    state_code=16  court_code=3  caseStatusSearchType=CLcauselist
    causelist_date=12-10-2026  captcha=<solved>
    Referer: https://hcservices.ecourts.gov.in/hcservices/main.php

- `00_meta_table.html` - the raw response (table.causelistTbl). 55 index rows.
- PDF actually downloaded: `Daily_List_THE_HON_BLE_RAVINDRA_VITHALRAO_GHUGE_CHIEF_JUSTICE_HON_BLE_.pdf`  (list type: Daily List; bench label: THE HON'BLE RAVINDRA VITHALRAO GHUGE, CHIEF JUSTICE, HON'BLE JUSTICE OM NARAYAN RAI)
- PDF URL: https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=vYIEIxvKPQlMx%2Bo3%2BxZ3Bur058R4mYHnKykluqUPbM4%3D&causelistYear=2026
- PDF present on the portal: yes
- PDF fetched at: 2026-10-10T20:47:54.348037+05:30
- Saved verbatim after cutting any bytes before the `%PDF` header (the portal prepends a UTF-8 BOM).

- **Trimmed fixture:** `Daily_List_THE_HON_BLE_RAVINDRA_VITHALRAO_GHUGE_CHIEF_JUSTICE_HON_BLE_.pdf` is pages 1-2 of 3 of the original PDF (original 125,635 bytes, sha256 `0138dd71404e09d501e556db963b312c1f9792947f78d950967d2a57fca4ab06`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.
