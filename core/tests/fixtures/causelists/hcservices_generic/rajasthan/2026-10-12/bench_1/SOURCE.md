# SOURCE - hcservices rajasthan (bench 1) list date 2026-10-12

Fetched live from the eCourts HC Services portal on 2026-10-10 (IST), around 20:49.

**Meta-table request** (CAPTCHA solved by bharat-courts' ddddocr solver, new session per attempt):

    POST https://hcservices.ecourts.gov.in/hcservices/cases_qry/index_qry.php
    action_code=showCauseList  flag=civ_t  selprevdays=0
    state_code=9  court_code=1  caseStatusSearchType=CLcauselist
    causelist_date=12-10-2026  captcha=<solved>
    Referer: https://hcservices.ecourts.gov.in/hcservices/main.php

- `00_meta_table.html` - the raw response (table.causelistTbl). 50 index rows.
- PDF actually downloaded: `Daily_Part_A_SANJAY_K_AGRAWAL_BALJINDER_SINGH_SANDHU.pdf`  (list type: Daily Part - A; bench label: SANJAY K. AGRAWAL, BALJINDER SINGH SANDHU)
- PDF URL: https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=m2INF0LcU7slnhTaJ0JLWLv8EYmzo%2Fry1KgWWePp0ys%3D&causelistYear=2026
- PDF present on the portal: yes
- PDF fetched at: 2026-10-10T20:49:36.717308+05:30
- Saved verbatim after cutting any bytes before the `%PDF` header (the portal prepends a UTF-8 BOM).

- **Trimmed fixture:** `Daily_Part_A_SANJAY_K_AGRAWAL_BALJINDER_SINGH_SANDHU.pdf` is pages 1-2 of 8 of the original PDF (original 558,719 bytes, sha256 `c346e1d72379aa169554c89421b817c41d1a533d92144ce9b2c5b83b6cd58183`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.
