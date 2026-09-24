# Real eCourts captures

Captured 23 Sep 2026 from the live portals, not hand-written. The case is
WP/26147/2026 (Telangana High Court, CNR HBHC010536082026). It is the case
whose order 2 was stored twice in production.

| File | What it is |
|---|---|
| `hc_cnr_HBHC010536082026.html` | The HC Services CNR-search page (`cases_qry/index_qry.php`, `action_code=fetchStateDistCourtNew`) as `EcourtsProvider._hc_cnr_search` returns it: case details ("Case disposed", "Contested--DISPOSED OF NO COSTS"), `history_table`, and the `order_table` listing orders 1-4 (07, 13, 14, 17 Aug 2026). The `display_pdf.php` tokens in it are session-bound and dead. |
| `order_HBHC010536082026_3_2026-08-14.txt` | PyPDF2 text of order 3, a one-page interim proceeding sheet ("List the matter on 17.08.2026 ... for pronouncement of orders"). |
| `order_HBHC010536082026_4_2026-08-17.txt` | PyPDF2 text of order 4, the final order ("this Writ Petition is disposed of", "miscelianeous petitions, pending if any, stand closed", "DISPOSING OF THE WRIT PETITION"). This is the court's own OCR text layer, spelling damage included. The petitioner's guardian, age and home address are redacted (the petitioner is a minor). Nothing else is changed. |

Two findings from the capture that the tests pin down:

- **Order numbers are positions, not identities.** The portal numbers the
  Orders table 1..n by date when it renders. When an order is uploaded late,
  every later order shifts up a number. That is how the 14 Aug order was
  stored as both "order 2" and "order 3". The earlier listing (before the
  13 Aug upload) can't be re-fetched. `test_order_renumbering.py` builds it
  from this capture by deleting the 13 Aug row and renumbering, which is
  exactly what the portal showed then.
- **The PDFs never hash alike.** The portal generates each download fresh
  (mPDF), with a new `/CreationDate` and `/ID` every time. Two downloads of
  order 3, ten seconds apart, were 212,605 bytes each with different
  SHA-256s. So "same order" is proven by extracted text, never by
  `content_hash`.
