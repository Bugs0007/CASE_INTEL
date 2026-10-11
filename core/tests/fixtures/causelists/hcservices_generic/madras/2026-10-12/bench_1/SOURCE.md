# SOURCE - hcservices madras (bench 1) list date 2026-10-12

Fetched live from the eCourts HC Services portal on 2026-10-10 (IST), around 20:34.

**Meta-table request** (CAPTCHA solved by bharat-courts' ddddocr solver, new session per attempt):

    POST https://hcservices.ecourts.gov.in/hcservices/cases_qry/index_qry.php
    action_code=showCauseList  flag=civ_t  selprevdays=0
    state_code=10  court_code=1  caseStatusSearchType=CLcauselist
    causelist_date=12-10-2026  captcha=<solved>
    Referer: https://hcservices.ecourts.gov.in/hcservices/main.php

- `00_meta_table.html` - the raw response (table.causelistTbl). 63 index rows.
- PDF actually downloaded: `Regular_List__Honourable_The_CHIEF_JUSTICE__Honourable__Mr_Justice_G_ARUL_MURUGA.pdf`  (list type: Regular List; bench label: Honourable The CHIEF JUSTICE, Honourable  Mr.Justice G.ARUL MURUGAN)
- PDF URL: https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=SuK85%2BPLdQmTC%2BEX2lmvEQyW0dk9uFRGqI5Nby3I9%2BA%3D&causelistYear=2026
- PDF present on the portal: yes
- PDF fetched at: 2026-10-10T20:34:50+05:30
- Saved verbatim after cutting any bytes before the `%PDF` header (the portal prepends a UTF-8 BOM).

- **Trimmed fixture:** `Regular_List__Honourable_The_CHIEF_JUSTICE__Honourable__Mr_Justice_G_ARUL_MURUGA.pdf` is pages 1-2 of 18 of the original PDF (original 68,808 bytes, sha256 `3dafc3159d3b05ee36b42c9e8be8afb117f2d450f6962f73625b4f86cc81d99e`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.
