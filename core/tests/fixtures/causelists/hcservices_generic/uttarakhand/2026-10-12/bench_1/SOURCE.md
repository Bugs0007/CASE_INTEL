# SOURCE - hcservices uttarakhand (bench 1) list date 2026-10-12

Fetched live from the eCourts HC Services portal on 2026-10-10 (IST), around 20:50.

**Meta-table request** (CAPTCHA solved by bharat-courts' ddddocr solver, new session per attempt):

    POST https://hcservices.ecourts.gov.in/hcservices/cases_qry/index_qry.php
    action_code=showCauseList  flag=civ_t  selprevdays=0
    state_code=15  court_code=1  caseStatusSearchType=CLcauselist
    causelist_date=12-10-2026  captcha=<solved>
    Referer: https://hcservices.ecourts.gov.in/hcservices/main.php

- `00_meta_table.html` - the raw response (table.causelistTbl). 9 index rows.
- PDF actually downloaded: `DAILY_CAUSE_LIST_Hon_ble_Mr_Justice_Manoj_Kumar_Tiwari_Hon_ble_Mr_Just.pdf`  (list type: DAILY CAUSE LIST; bench label: Hon'ble Mr. Justice Manoj Kumar Tiwari, Hon'ble Mr. Justice Subhash Upadhyay)
- PDF URL: https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=Kv9Z4cmVoBvFzPAwNuyhHhvEjBS98cfCrtTEGdxTvig%3D&causelistYear=2026
- PDF present on the portal: yes
- PDF fetched at: 2026-10-10T20:50:00.504769+05:30
- Saved verbatim after cutting any bytes before the `%PDF` header (the portal prepends a UTF-8 BOM).

- **Trimmed fixture:** `DAILY_CAUSE_LIST_Hon_ble_Mr_Justice_Manoj_Kumar_Tiwari_Hon_ble_Mr_Just.pdf` is pages 1-2 of 18 of the original PDF (original 78,983 bytes, sha256 `1b8db8240e9408420d488d1e335915c5abe49c742b6f6c8c1e1d9cd48dd0abe5`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.
