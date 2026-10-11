# SOURCE - hcservices karnataka (bench 2) list date 2026-10-12

Fetched live from the eCourts HC Services portal on 2026-10-10 (IST), around 20:48.

**Meta-table request** (CAPTCHA solved by bharat-courts' ddddocr solver, new session per attempt):

    POST https://hcservices.ecourts.gov.in/hcservices/cases_qry/index_qry.php
    action_code=showCauseList  flag=civ_t  selprevdays=0
    state_code=3  court_code=2  caseStatusSearchType=CLcauselist
    causelist_date=12-10-2026  captcha=<solved>
    Referer: https://hcservices.ecourts.gov.in/hcservices/main.php

- `00_meta_table.html` - the raw response (table.causelistTbl). 19 index rows.
- PDF actually downloaded: `Cause_List_No_1_M_NAGAPRASANNA_HEMA_KULKARNI.pdf`  (list type: Cause List No. 1; bench label: M.NAGAPRASANNA, HEMA KULKARNI)
- PDF URL: https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=PIYMGWuymRNbNOkLv4DK%2BCp4HnMix5QodhyABRQVfc8%3D&causelistYear=2026
- PDF present on the portal: yes
- PDF fetched at: 2026-10-10T20:48:53.199620+05:30
- Saved verbatim after cutting any bytes before the `%PDF` header (the portal prepends a UTF-8 BOM).

- **Trimmed fixture:** `Cause_List_No_1_M_NAGAPRASANNA_HEMA_KULKARNI.pdf` is pages 1-2 of 14 of the original PDF (original 93,181 bytes, sha256 `cc4ffaa889d5d834a4b36d6b7725612b3cfd7f844207aeffb42b78e52a604259`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.
