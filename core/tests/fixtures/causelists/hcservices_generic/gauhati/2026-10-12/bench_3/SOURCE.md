# SOURCE - hcservices gauhati (bench 3) list date 2026-10-12

Fetched live from the eCourts HC Services portal on 2026-10-10 (IST), around 20:48.

**Meta-table request** (CAPTCHA solved by bharat-courts' ddddocr solver, new session per attempt):

    POST https://hcservices.ecourts.gov.in/hcservices/cases_qry/index_qry.php
    action_code=showCauseList  flag=civ_t  selprevdays=0
    state_code=6  court_code=3  caseStatusSearchType=CLcauselist
    causelist_date=12-10-2026  captcha=<solved>
    Referer: https://hcservices.ecourts.gov.in/hcservices/main.php

- `00_meta_table.html` - the raw response (table.causelistTbl). 6 index rows.
- PDF actually downloaded: `Daily_HONOURABLE_MR_JUSTICE_MICHAEL_ZOTHANKHUMA.pdf`  (list type: Daily; bench label: HONOURABLE MR. JUSTICE MICHAEL ZOTHANKHUMA)
- PDF URL: https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=6ck%2B%2B2aSfhA1uTL%2F34%2FKKgAHP3qzXwHpEkrowCKBsDQ%3D&causelistYear=2026
- PDF present on the portal: yes
- PDF fetched at: 2026-10-10T20:48:13.771828+05:30
- Saved verbatim after cutting any bytes before the `%PDF` header (the portal prepends a UTF-8 BOM).

- **Trimmed fixture:** `Daily_HONOURABLE_MR_JUSTICE_MICHAEL_ZOTHANKHUMA.pdf` is pages 1-2 of 2 of the original PDF (original 284,548 bytes, sha256 `9bbac4a7d88acdfaa9ed7af1b2166c85ffaf602b47b2ff3306ce6192914177bf`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.
