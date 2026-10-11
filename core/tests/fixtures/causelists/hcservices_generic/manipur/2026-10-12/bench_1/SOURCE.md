# SOURCE - hcservices manipur (bench 1) list date 2026-10-12

Fetched live from the eCourts HC Services portal on 2026-10-10 (IST), around 20:49.

**Meta-table request** (CAPTCHA solved by bharat-courts' ddddocr solver, new session per attempt):

    POST https://hcservices.ecourts.gov.in/hcservices/cases_qry/index_qry.php
    action_code=showCauseList  flag=civ_t  selprevdays=0
    state_code=25  court_code=1  caseStatusSearchType=CLcauselist
    causelist_date=12-10-2026  captcha=<solved>
    Referer: https://hcservices.ecourts.gov.in/hcservices/main.php

- `00_meta_table.html` - the raw response (table.causelistTbl). 6 index rows.
- PDF actually downloaded: `Daily_Hon_ble_The_Chief_Justice_Hon_ble_Mr_Justice_Ahanthem_Bimol_Sing.pdf`  (list type: Daily; bench label: Hon'ble The Chief Justice, Hon'ble Mr Justice Ahanthem Bimol Singh)
- PDF URL: https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=wqoG2Flu4QgtRHnYCGlWpn0cW%2BEQoVTseBmYJcBzUsQ%3D&causelistYear=2026
- PDF present on the portal: yes
- PDF fetched at: 2026-10-10T20:49:12.645409+05:30
- Saved verbatim after cutting any bytes before the `%PDF` header (the portal prepends a UTF-8 BOM).

- **Trimmed fixture:** `Daily_Hon_ble_The_Chief_Justice_Hon_ble_Mr_Justice_Ahanthem_Bimol_Sing.pdf` is pages 1-2 of 3 of the original PDF (original 93,321 bytes, sha256 `59438046cdab3d5d5624da4ea2e8d88a75a17cf25cc5ede930f1646442e98352`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.
