# SOURCE - hcservices karnataka (bench 1) list date 2026-10-12

Fetched live from the eCourts HC Services portal on 2026-10-10 (IST), around 20:35.

**Meta-table request** (CAPTCHA solved by bharat-courts' ddddocr solver, new session per attempt):

    POST https://hcservices.ecourts.gov.in/hcservices/cases_qry/index_qry.php
    action_code=showCauseList  flag=civ_t  selprevdays=0
    state_code=3  court_code=1  caseStatusSearchType=CLcauselist
    causelist_date=12-10-2026  captcha=<solved>
    Referer: https://hcservices.ecourts.gov.in/hcservices/main.php

- `00_meta_table.html` - the raw response (table.causelistTbl). 66 index rows.
- PDF actually downloaded: `Cause_List_No__3__CHIEF_JUSTICE__K_S__HEMALEKHA.pdf`  (list type: Cause List No. 3; bench label: CHIEF JUSTICE, K.S. HEMALEKHA)
- PDF URL: https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=6QvefvkXB1vEvye4fwHtbiSr064c4UEFbuI5UIVnwrc%3D&causelistYear=2026
- PDF present on the portal: yes
- PDF fetched at: 2026-10-10T20:35:09+05:30
- Saved verbatim after cutting any bytes before the `%PDF` header (the portal prepends a UTF-8 BOM).

- **Trimmed fixture:** `Cause_List_No__3__CHIEF_JUSTICE__K_S__HEMALEKHA.pdf` is pages 1-2 of 2 of the original PDF (original 77,024 bytes, sha256 `6aa16215d34891d0e91f30d7b7daad2a072ecc530cca9b2679d110eee1464f8e`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.
