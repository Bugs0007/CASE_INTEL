# SOURCE - district_ecourts (services.ecourts.gov.in)

All files were fetched live on 2026-10-10 (IST) from the eCourts District Courts portal, https://services.ecourts.gov.in/ecourtindia_v6/ , using the project's `_TokenSeedingDistrictClient` (home-page GET for cookies, per-session `delimeter` headers scraped from `/js/components.js`, `app_token` from `?p=casestatus/index`) and bharat-courts' ddddocr CAPTCHA solver.

Request sequence per court (each `submitCauseList` is its own CAPTCHA-gated request; the portal serves ONE court (judge) per request):

    POST ?p=cause_list/fillCauseList   state_code, dist_code, court_complex_code, est_code, search_act=   -> court dropdown (`meta.json["courts"]`)
    POST ?p=cause_list/submitCauseList CL_court_no=<est>^<court_no>, causelist_date=DD-MM-YYYY, cause_list_captcha_code=<solved>,
                                       court_name_txt=<dropdown label>, state_code, dist_code, court_complex_code, est_code,
                                       cicri=civ|cri, selprevdays=0|1

The response JSON key holding the table HTML is `case_data` (bharat-courts 0.3.0 reads `causelist_data`/`cause_list_data`, so its `DistrictCourtClient.cause_list()` silently returns [] for every court).

| directory | state/dist/complex | date | files |
|---|---|---|---|
| `district_ecourts/2026-10-09/telangana_hyd_city_civil` | 29/2/1290019 (HYD, City Civil Court Complex) | 09-10-2026 | 2_1_civ.json, 2_1_cri.json, 2_3_civ.json (fetched 2026-10-10T20:38:09) |
| `district_ecourts/2026-10-09/telangana_hyd_criminal` | 29/2/1290022 (HYD, Criminal Court Complex) | 09-10-2026 | 3_1_cri.json, 3_2_cri.json (fetched 2026-10-10T20:40:17) |
| `district_ecourts/2026-10-12/karnataka_blr_city_civil` | 3/20/1030135 (City Civil Court Complex, Bangalore) | 12-10-2026 | 3_1_civ.json (fetched 2026-10-10T20:44:10) |
| `district_ecourts/2026-10-12/telangana_hyd_city_civil` | 29/2/1290019 (HYD, City Civil Court Complex) | 12-10-2026 | 2_1_civ.json (fetched 2026-10-10T20:39:47) |

`*_cri.json` containing only `Record not found` (101 bytes) is the portal's genuine 'nothing listed' answer for that court/mode; it is kept as the empty-list fixture.

## cnr_case_page/TSHC010030082026.html
Raw `casetype_list` HTML of `POST ?p=cnr_status/searchByCNR` (cino=TSHC010030082026, CAPTCHA solved), fetched 2026-10-10 ~20:39 IST via `EcourtsProvider._district_cnr_search`. A public record chosen only because the CNR appears in the 2026-10-09 City Civil Court list fixture above. It shows what a CNR-tracked district case already exposes: `Court Number and Judge`, the establishment name, and a link carrying `state_code=29&dist_code=2&court_code=2` (the establishment code) - but NOT the court-complex code.

Party and advocate names in these files are as published by the courts; they are public cause-list data.
## complexes.json
The captcha-free `casestatus/fillcomplex` dropdown for Telangana / Hyderabad CCC (state 29, district 2) and Karnataka / Bengaluru (state 3, district 20), fetched 2026-10-10T22:48:48+05:30 via `EcourtsProvider.list_complexes`. Values are `<complex code>@<establishment codes>@<needs-est flag>`; used to test which complex holds an establishment.
