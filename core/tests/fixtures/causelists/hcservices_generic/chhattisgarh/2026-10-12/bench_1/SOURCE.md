# SOURCE - hcservices chhattisgarh (bench 1) list date 2026-10-12

Fetched live from the eCourts HC Services portal on 2026-10-10 (IST), around 20:48.

**Meta-table request** (CAPTCHA solved by bharat-courts' ddddocr solver, new session per attempt):

    POST https://hcservices.ecourts.gov.in/hcservices/cases_qry/index_qry.php
    action_code=showCauseList  flag=civ_t  selprevdays=0
    state_code=18  court_code=1  caseStatusSearchType=CLcauselist
    causelist_date=12-10-2026  captcha=<solved>
    Referer: https://hcservices.ecourts.gov.in/hcservices/main.php

- `00_meta_table.html` - the raw response (table.causelistTbl). 59 index rows.
- PDF actually downloaded: `FRESH_MATTERS_FILING_Hon_ble_The_Chief_Justice_Hon_ble_Shri_Justice_Sa.pdf`  (list type: FRESH MATTERS (FILING); bench label: Hon'ble The Chief Justice, Hon'ble Shri Justice Santosh Sharma)
- PDF URL: https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=FoITEur%2BLKA9h2%2BfWdYR64SGgrjQrB%2B8is56p%2FhClGg%3D&causelistYear=2026
- PDF present on the portal: yes
- PDF fetched at: 2026-10-10T20:48:00.645546+05:30
- Saved verbatim after cutting any bytes before the `%PDF` header (the portal prepends a UTF-8 BOM).

- **Trimmed fixture:** `FRESH_MATTERS_FILING_Hon_ble_The_Chief_Justice_Hon_ble_Shri_Justice_Sa.pdf` is pages 1-2 of 7 of the original PDF (original 56,519 bytes, sha256 `01f05f81f3de3c6c224629cf942452a302388c973667cb78c711cbea0e5bd8cb`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.
