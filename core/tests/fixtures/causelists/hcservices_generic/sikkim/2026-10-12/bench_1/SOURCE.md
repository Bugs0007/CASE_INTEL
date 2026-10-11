# SOURCE - hcservices sikkim (bench 1) list date 2026-10-12

Fetched live from the eCourts HC Services portal on 2026-10-10 (IST), around 20:49.

**Meta-table request** (CAPTCHA solved by bharat-courts' ddddocr solver, new session per attempt):

    POST https://hcservices.ecourts.gov.in/hcservices/cases_qry/index_qry.php
    action_code=showCauseList  flag=civ_t  selprevdays=0
    state_code=24  court_code=1  caseStatusSearchType=CLcauselist
    causelist_date=12-10-2026  captcha=<solved>
    Referer: https://hcservices.ecourts.gov.in/hcservices/main.php

- `00_meta_table.html` - the raw response (table.causelistTbl). 1 index rows.
- PDF actually downloaded: `Daily_Hon_ble_The_Chief_Justice_Mr_A_Muhamed_Mustaque.pdf`  (list type: Daily; bench label: Hon'ble The Chief Justice Mr. A. Muhamed Mustaque)
- PDF URL: https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=%2B%2F6OVd6cbVKEguvVIbV5ekbvMsl9tqOeFl5L%2FiAZdXk%3D&causelistYear=2026
- PDF present on the portal: yes
- PDF fetched at: 2026-10-10T20:49:42.945355+05:30
- Saved verbatim after cutting any bytes before the `%PDF` header (the portal prepends a UTF-8 BOM).

- **Trimmed fixture:** `Daily_Hon_ble_The_Chief_Justice_Mr_A_Muhamed_Mustaque.pdf` is pages 1-2 of 2 of the original PDF (original 341,849 bytes, sha256 `c62885d0e1bf7f9d3a7befb98641f9be5706d4d35888f28943b8e86e3551f66f`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.
