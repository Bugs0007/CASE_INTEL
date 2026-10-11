# SOURCE - hcservices patna (bench 1) list date 2026-10-09

Fetched live from the eCourts HC Services portal on 2026-10-10 (IST), around 20:49.

**Meta-table request** (CAPTCHA solved by bharat-courts' ddddocr solver, new session per attempt):

    POST https://hcservices.ecourts.gov.in/hcservices/cases_qry/index_qry.php
    action_code=showCauseList  flag=civ_t  selprevdays=1
    state_code=8  court_code=1  caseStatusSearchType=CLcauselist
    causelist_date=09-10-2026  captcha=<solved>
    Referer: https://hcservices.ecourts.gov.in/hcservices/main.php

- `00_meta_table.html` - the raw response (table.causelistTbl). 45 index rows.
- PDF actually downloaded: `Daily_The_Chief_Justice_Mr_Justice_Partha_Sarthy.pdf`  (list type: Daily; bench label: The Chief Justice, Mr. Justice Partha Sarthy)
- PDF URL: https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=TzZg08hrAT%2BjE%2BpUaO8vKd0wu8N4N7MS3JuJef0y3hw%3D&causelistYear=2026
- PDF present on the portal: yes
- PDF fetched at: 2026-10-10T20:49:30.253999+05:30
- Saved verbatim after cutting any bytes before the `%PDF` header (the portal prepends a UTF-8 BOM).

- **Trimmed fixture:** `Daily_The_Chief_Justice_Mr_Justice_Partha_Sarthy.pdf` is pages 1-2 of 3 of the original PDF (original 51,398 bytes, sha256 `945aaa4ba3273092dd2a12f67802f99f2a535412495c78f2ab34e9bfb3b71dfd`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.
