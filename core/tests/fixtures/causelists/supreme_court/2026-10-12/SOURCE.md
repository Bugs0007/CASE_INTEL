# SOURCE - supreme_court (api.sci.gov.in)

Fetched live on 2026-10-10 (IST), ~20:42, with plain `curl` (no CAPTCHA, no cookies, `User-Agent: Mozilla/5.0`).

- `index_page.html` - `GET https://www.sci.gov.in/cause-list/`. The "Published Cause List" tab is a plain HTML table (rows = listing dates, columns = ADVANCE / MISCELLANEOUS main+suppl. / REGULAR main+suppl. / WEEKLY) whose cells are anchors to the PDFs. THIS is the file-name index: no search form or CAPTCHA is involved for daily lists. (The form on the same page - search by AOR code / party / court / judge - is a separate, CAPTCHA-gated flow.)
- `M_J_1.pdf` - `GET https://api.sci.gov.in/jonew/cl/2026-10-12/M_J_1.pdf` (Miscellaneous, main, 248 pages, 968,264 bytes). Response headers: HTTP/1.1 200 OK; Date: Sat, 10 Oct 2026 15:12:57 GMT; Server: Apache/2.4.25 (Debian); Last-Modified: Sat, 10 Oct 2026 08:53:54 GMT; ETag: "ec648-65d789ac8295b"; Accept-Ranges: bytes; Content-Length: 968264; Content-Type: application/pdf
- `M_J_2.pdf` - `GET https://api.sci.gov.in/jonew/cl/2026-10-12/M_J_2.pdf` (Miscellaneous, supplementary, 587,327 bytes). Response headers: HTTP/1.1 200 OK; Date: Sat, 10 Oct 2026 15:13:06 GMT; Server: Apache/2.4.25 (Debian); Last-Modified: Sat, 10 Oct 2026 12:27:19 GMT; ETag: "8f63f-65d7b95fdf1b9"; Accept-Ranges: bytes; Content-Length: 587327; Content-Type: application/pdf

`Last-Modified` is the observable publish time: the 12 Oct main list was uploaded Sat 10 Oct 08:53 GMT (14:23 IST) and the supplementary 12:27 GMT.

- **Trimmed fixture:** `M_J_1.pdf` is pages 1-3 of 248 of the original PDF (original 968,264 bytes, sha256 `66ada7bd6da23736b6d5046742b37cb00521f20b87cf67456abaf5e04564ceb8`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.

- **Trimmed fixture:** `M_J_2.pdf` is pages 1-3 of 44 of the original PDF (original 587,327 bytes, sha256 `1ef12e70d753e30a516d21c25a494a514fc935dc2df11c29fa94badb9578fe10`), cut with PyPDF2 so the tests carry only the pages they need. Page content is the portal's, unmodified.
