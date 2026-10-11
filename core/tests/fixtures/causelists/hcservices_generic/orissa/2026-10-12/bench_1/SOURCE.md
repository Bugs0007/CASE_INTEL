# SOURCE - hcservices orissa (bench 1) list date 2026-10-12

Fetched live from the eCourts HC Services portal on 2026-10-10 (IST), around 20:49.

**Meta-table request** (CAPTCHA solved by bharat-courts' ddddocr solver, new session per attempt):

    POST https://hcservices.ecourts.gov.in/hcservices/cases_qry/index_qry.php
    action_code=showCauseList  flag=civ_t  selprevdays=0
    state_code=11  court_code=1  caseStatusSearchType=CLcauselist
    causelist_date=12-10-2026  captcha=<solved>
    Referer: https://hcservices.ecourts.gov.in/hcservices/main.php

- `00_meta_table.html` - the raw response (table.causelistTbl). 13 index rows.
- PDF actually downloaded: `Weekly_Daily_MR_JUSTICE_HARISH_TANDON_CJ_MR_JUSTICE_CHITTARANJAN_DASH.pdf`  (list type: Weekly Daily; bench label: MR. JUSTICE HARISH TANDON (CJ), MR. JUSTICE CHITTARANJAN DASH)
- PDF URL: https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=AIMJ8m5wRDUz5Ge%2BeRAUbWNS0KeVkWA7Rcb9pflz6ck%3D&causelistYear=2026
- PDF present on the portal: yes
- PDF fetched at: 2026-10-10T20:49:24.403699+05:30
- Saved verbatim after cutting any bytes before the `%PDF` header (the portal prepends a UTF-8 BOM).

- **Trimmed fixture:** `Weekly_Daily_MR_JUSTICE_HARISH_TANDON_CJ_MR_JUSTICE_CHITTARANJAN_DASH.pdf` is pages 1-2 of 8 of the original PDF (original 57,976 bytes, sha256 `163e27b5fdb771da7139a32c2734bd050fa54dfc6d886d91e5a0aabb2d849157`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.
