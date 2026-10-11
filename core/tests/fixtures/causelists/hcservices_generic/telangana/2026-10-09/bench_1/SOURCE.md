# SOURCE - hcservices telangana (bench 1) list date 2026-10-09

Fetched live from the eCourts HC Services portal on 2026-10-10 (IST), around 20:54.

**Meta-table request** (CAPTCHA solved by bharat-courts' ddddocr solver, new session per attempt):

    POST https://hcservices.ecourts.gov.in/hcservices/cases_qry/index_qry.php
    action_code=showCauseList  flag=civ_t  selprevdays=1
    state_code=29  court_code=1  caseStatusSearchType=CLcauselist
    causelist_date=09-10-2026  captcha=<solved>
    Referer: https://hcservices.ecourts.gov.in/hcservices/main.php

- `00_meta_table.html` - the raw response (table.causelistTbl). 48 index rows.
- PDF actually downloaded: `DAILY_LIST_P_SAM_KOSHY.pdf`  (list type: DAILY LIST; bench label: P.SAM KOSHY)
- PDF URL: https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=SMNc3ggCPAgK2yCWv0XdYhO4IQxpvGs21heFHZ0QnrE%3D&causelistYear=2026
- PDF present on the portal: yes
- PDF fetched at: 2026-10-10T20:54:31.768234+05:30
- Saved verbatim after cutting any bytes before the `%PDF` header (the portal prepends a UTF-8 BOM).

- **Trimmed fixture:** `DAILY_LIST_P_SAM_KOSHY.pdf` is pages 1-2 of 21 of the original PDF (original 117,161 bytes, sha256 `590e9e6e0b1b126fdb7736e07614217e51cf126a2d26cc1fa5444fdd968c6258`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.
