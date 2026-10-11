# SOURCE - hcservices delhi (bench 1) list date 2026-10-12

Fetched live from the eCourts HC Services portal on 2026-10-10 (IST), around 20:48.

**Meta-table request** (CAPTCHA solved by bharat-courts' ddddocr solver, new session per attempt):

    POST https://hcservices.ecourts.gov.in/hcservices/cases_qry/index_qry.php
    action_code=showCauseList  flag=civ_t  selprevdays=0
    state_code=26  court_code=1  caseStatusSearchType=CLcauselist
    causelist_date=12-10-2026  captcha=<solved>
    Referer: https://hcservices.ecourts.gov.in/hcservices/main.php

- `00_meta_table.html` - the raw response (table.causelistTbl). 54 index rows.
- PDF actually downloaded: `COMPLETE_CAUSE_LIST_CASES_PERTAINING_TO_SPECIAL_BENCHES.pdf`  (list type: COMPLETE CAUSE LIST; bench label: CASES PERTAINING TO SPECIAL BENCHES)
- PDF URL: https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=sVtMEPr3X0S2HB4WJbuzz97mbehtAtMPO1Vgxu9bHRE%3D&causelistYear=2026
- PDF present on the portal: yes
- PDF fetched at: 2026-10-10T20:48:06.966635+05:30
- Saved verbatim after cutting any bytes before the `%PDF` header (the portal prepends a UTF-8 BOM).

- **Trimmed fixture:** `COMPLETE_CAUSE_LIST_CASES_PERTAINING_TO_SPECIAL_BENCHES.pdf` is pages 1-2 of 2 of the original PDF (original 3,802 bytes, sha256 `744da350c2798bf716511a8d7a9667cfefeea96998759c0e6b6b0c89033f97cc`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.

## Additional Delhi lists (fetched 2026-10-10 ~22:30 IST, same flow, same 12 Oct index)

The first PDF above is index row 0 ('CASES PERTAINING TO SPECIAL BENCHES'). To test the parser on the kinds of list Delhi actually publishes, these index rows were also downloaded in the same session (index re-fetched; 54 rows again):

- `row01_CASES_PERTAINING_TO_SPL_DIVISION_BENCHES.pdf`: index row 1 ('CASES PERTAINING TO SPL.DIVISION BENCHES'), URL https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=0ykE3ki5BjsWz2jb9gySPrzBXqecQjeJq55PlIM%2F9t0%3D&causelistYear=2026; pages 1-2 of 17; original 19,083 bytes sha256 `ee1eb826d2cbd50c8ad07e04c5e8b3824893ea37fe852a8a5d8da0e857a0b9da`.
- `row02_JOINT_REGISTRAR_JUDICIAL_SH_ANIL_KUMAR_D.pdf`: index row 2 ('JOINT REGISTRAR (JUDICIAL) SH. ANIL KUMAR (DHJS)'), URL https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=mFqTJiIbRa3ZgXhwfjGcXLUPMfUG8AcOdVTHHvu4ImM%3D&causelistYear=2026; pages 1-1 of 1; original 2,260 bytes sha256 `a3962ae27236792927d62799680b4959d68a831e3e961b580eb18b017beb3c6b`.
- `row05_HON_BLE_MR_JUSTICE_NAVIN_CHAWLA_HON_BLE_.pdf`: index row 5 ('HON'BLE MR. JUSTICE NAVIN CHAWLA, HON'BLE MR. JUSTICE ARUN BHARDWAJ'), URL https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=qrzqOw%2B2s7915gqHE7IlZQPoRWpf166ZjbM5jIwvDI0%3D&causelistYear=2026; pages 1-2 of 12; original 14,726 bytes sha256 `224f09d7bf9baaaa303e6990d0c5d4a6c09be06da28366bd4d21af01c19198b5`.
- `row10_HON_BLE_MR_JUSTICE_AMIT_MAHAJAN.pdf`: index row 10 ('HON'BLE MR. JUSTICE AMIT MAHAJAN'), URL https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=fsWBaoEitQvGSlXpMXK1xuOqDkTZbk%2FC5hBBugJHZY0%3D&causelistYear=2026; pages 1-2 of 18; original 29,714 bytes sha256 `1fa054769f6d486c89eb94e0f9cda11337ebe0a5c8032fa9b12e5529457d3032`.
- `row20_JOINT_REGISTRAR_JUDICIAL_SH_ASHOK_KUMAR.pdf`: index row 20 ('JOINT REGISTRAR (JUDICIAL) SH. ASHOK KUMAR'), URL https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=15KrkgIa2d%2B1BF%2ByMbnTg%2FDqP4buI9skT%2BglNb2ZzPs%3D&causelistYear=2026; pages 1-2 of 11; original 17,629 bytes sha256 `94a1250004803379a28141fdb8cd781656050886a51af603866c090949933a29`.
