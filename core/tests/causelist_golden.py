"""Golden expectations for every hcservices list captured live on 2026-10-10.

Each row is what the parser read out of one REAL PDF (core/tests/fixtures/causelists/
hcservices_generic/<court>/<date>/<bench>/<file>). The fixtures are trimmed to the pages
the tests need (see each SOURCE.md), so `count` is the number of matters on THOSE pages.
The entries were checked by eye against the row dumps of the same PDFs; the point of the
table is that any later change to a parser that moves one of these numbers is a visible,
reviewable diff.
"""

GOLDEN = {
    ("andhra", "2026-10-12", "bench_1", "FRESH_MOTION_HEARING__LISA_GILL__CHALLA_GUNARANJAN.pdf"): dict(
        parser="f1", count=49, date="2026-10-12", hall="1",
        first=("1", "WA/1179/2026"),
        mid=("25", "WP/6121/2010"),
        last=("49", "WA/121445/2014/ (Filing No.)"),
    ),
    ("bombay", "2026-10-09", "bench_1", "Daily_Main__HON_BLE_THE_CHIEF_JUSTICE__HON_BLE_JUSTICE_ADVAIT_M__SETHNA.pdf"): dict(
        parser="f2", count=4, date="2026-10-09", hall="46",
        first=("1", "WP/15506/2025"),
        mid=("1 (connected)", "WP/3687/2026"),
        last=("1 (connected)", "WP/3305/2026"),
    ),
    ("bombay", "2026-10-12", "bench_1", "Daily_Main_HON_BLE_THE_CHIEF_JUSTICE_HON_BLE_JUSTICE_ADVAIT_M_SETHNA.pdf"): dict(
        parser="f2", count=9, date="2026-10-12", hall="46",
        first=("1", "WP(L)/34731/2026"),
        mid=("5", "WP/3769/2026"),
        last=("6 (connected)", "SCNW/7/2026"),
    ),
    ("calcutta", "2026-10-12", "bench_3", "Daily_List_THE_HON_BLE_RAVINDRA_VITHALRAO_GHUGE_CHIEF_JUSTICE_HON_BLE_.pdf"): dict(
        parser="f2", count=22, date="2026-10-12", hall="1",
        first=("1", "WPA(P)/477/2026"),
        mid=("wt12", "WPA(P)/91/2022"),
        last=("22", "MAT/1709/2026"),
    ),
    ("chhattisgarh", "2026-10-12", "bench_1", "FRESH_MATTERS_FILING_Hon_ble_The_Chief_Justice_Hon_ble_Shri_Justice_Sa.pdf"): dict(
        parser="f2", count=5, date="2026-10-12", hall="",
        first=("1", "WA 915/2026"),
        mid=("3", "WA 937/2026"),
        last=("5", "WA 953/2026"),
    ),
    ("delhi", "2026-10-12", "bench_1", "COMPLETE_CAUSE_LIST_CASES_PERTAINING_TO_SPECIAL_BENCHES.pdf"): dict(
        parser="f4", count=4, date="2026-10-12", hall="61",
        first=("1", "CA(COMM.IPD-CR)/1/2021"),
        mid=("3", "CS(COMM)/105/2026"),
        last=("4", "CS(COMM)/868/2026"),
    ),
    ("delhi", "2026-10-12", "bench_1", "row01_CASES_PERTAINING_TO_SPL_DIVISION_BENCHES.pdf"): dict(
        parser="f4", count=2, date="2026-10-12", hall="190",
        first=("1", "W.P.(C)/4859/2016"),
        mid=("2", "CONT.CAS(C)/1523/2025"),
        last=("2", "CONT.CAS(C)/1523/2025"),
    ),
    ("delhi", "2026-10-12", "bench_1", "row02_JOINT_REGISTRAR_JUDICIAL_SH_ANIL_KUMAR_D.pdf"): dict(
        parser="f4", count=2, date="2026-10-12", hall="71",
        first=("1", "CS(COMM)/97/2026"),
        mid=("2", "CS(COMM)/882/2026"),
        last=("2", "CS(COMM)/882/2026"),
    ),
    ("delhi", "2026-10-12", "bench_1", "row05_HON_BLE_MR_JUSTICE_NAVIN_CHAWLA_HON_BLE_.pdf"): dict(
        parser="f4", count=4, date="2026-10-12", hall="274",
        first=("1", "W.P.(CRL)/3134/2026"),
        mid=("3", "W.P.(CRL)/3183/2026"),
        last=("4", "W.P.(CRL)/3186/2026"),
    ),
    ("delhi", "2026-10-12", "bench_1", "row10_HON_BLE_MR_JUSTICE_AMIT_MAHAJAN.pdf"): dict(
        parser="f4", count=10, date="2026-10-12", hall="256",
        first=("1", "W.P.(C)/8569/2026"),
        mid=("6", "W.P.(C)/14420/2026"),
        last=("10", "W.P.(C)/13839/2019"),
    ),
    ("delhi", "2026-10-12", "bench_1", "row20_JOINT_REGISTRAR_JUDICIAL_SH_ASHOK_KUMAR.pdf"): dict(
        parser="f4", count=9, date="2026-10-12", hall="84",
        first=("1", "MAC.APP./122/2026"),
        mid=("5", "MAC.APP./127/2026"),
        last=("9", "MAC.APP./131/2026"),
    ),
    ("gauhati", "2026-10-12", "bench_3", "Daily_HONOURABLE_MR_JUSTICE_MICHAEL_ZOTHANKHUMA.pdf"): dict(
        parser="f2", count=11, date="2026-10-12", hall="1",
        first=("1", "WP(C)/150/2026"),
        mid=("6", "WP(C)/98/2024"),
        last=("11", "WP(C)/164/2025"),
    ),
    ("jammu", "2026-10-12", "bench_1", "Regular_HON_BLE_THE_CHIEF_JUSTICE_HON_BLE_MR_JUSTICE_RAJESH_SEKHRI.pdf"): dict(
        parser="f3", count=5, date="2026-10-12", hall="1",
        first=("1", "WP(C)PIL/17/2020"),
        mid=("3", "CCP(D)/19/2026"),
        last=("5", "WP(C)/18/2025"),
    ),
    ("karnataka", "2026-10-12", "bench_1", "Cause_List_No__3__CHIEF_JUSTICE__K_S__HEMALEKHA.pdf"): dict(
        parser="f2", count=2, date="2026-10-12", hall="1",
        first=("1", "WP 200448/2025"),
        mid=("1.1", "WP 25515/2025"),
        last=("1.1", "WP 25515/2025"),
    ),
    ("karnataka", "2026-10-12", "bench_2", "Cause_List_No_1_M_NAGAPRASANNA_HEMA_KULKARNI.pdf"): dict(
        parser="f2", count=12, date="2026-10-12", hall="2",
        first=("1", "WA 100580/2026"),
        mid=("7", "WA 100496/2026"),
        last=("12", "WP 108565/2026"),
    ),
    ("madras", "2026-10-12", "bench_1", "Regular_List__Honourable_The_CHIEF_JUSTICE__Honourable__Mr_Justice_G_ARUL_MURUGA.pdf"): dict(
        parser="f2", count=16, date="2026-10-12", hall="01",
        first=("1", "WA/801/2022"),
        mid=("7 (connected)", "WP/40447/2026"),
        last=("14", "WP/37319/2026"),
    ),
    ("manipur", "2026-10-12", "bench_1", "Daily_Hon_ble_The_Chief_Justice_Hon_ble_Mr_Justice_Ahanthem_Bimol_Sing.pdf"): dict(
        parser="f2", count=11, date="2026-10-12", hall="1",
        first=("1", "MC(WA)/66/2025"),
        mid=("6", "WP(C)/935/2017"),
        last=("10", "PIL/4/2026"),
    ),
    ("meghalaya", "2026-10-12", "bench_1", "DAILY_HON_BLE_JUSTICE_REVATI_MOHITE_DERE_CHIEF_JUSTICE.pdf"): dict(
        parser="f2", count=4, date="2026-10-12", hall="",
        first=("1", "Crl.Petn./103/2026"),
        mid=("3", "Crl.Petn./155/2026"),
        last=("4", "Crl.Petn./89/2026"),
    ),
    ("orissa", "2026-10-12", "bench_1", "Weekly_Daily_MR_JUSTICE_HARISH_TANDON_CJ_MR_JUSTICE_CHITTARANJAN_DASH.pdf"): dict(
        parser="f2", count=12, date="2026-10-12", hall="",
        first=("1", "WA/1244/2026"),
        mid=("7", "WPCRL/99/2026"),
        last=("12", "WPCRL/123/2026"),
    ),
    ("patna", "2026-10-09", "bench_1", "Daily_The_Chief_Justice_Mr_Justice_Partha_Sarthy.pdf"): dict(
        parser="f2", count=26, date="2026-10-09", hall="1",
        first=("1", "L.P.A/100/2025"),
        mid=("13", "CWJC/14221/2026"),
        last=("23", "L.P.A/113/2025"),
    ),
    ("rajasthan", "2026-10-12", "bench_1", "Daily_Part_A_SANJAY_K_AGRAWAL_BALJINDER_SINGH_SANDHU.pdf"): dict(
        parser="f2", count=8, date="2026-10-12", hall="",
        first=("1", "S.A.W. 592/2024"),
        mid=("5", "C.W. 13234/2016"),
        last=("8", "C.W. 9012/2018"),
    ),
    ("sikkim", "2026-10-12", "bench_1", "Daily_Hon_ble_The_Chief_Justice_Mr_A_Muhamed_Mustaque.pdf"): dict(
        parser="f2", count=5, date="2026-10-12", hall="1",
        first=("1", "WP(C)/32/2026"),
        mid=("3", "WP(C)/32/2025"),
        last=("5", "WP(C)/47/2026"),
    ),
    ("telangana", "2026-10-09", "bench_1", "DAILY_LIST_P_SAM_KOSHY.pdf"): dict(
        parser="f1", count=26, date="2026-10-09", hall="2",
        first=("1", "CRP/43392/2026/(Filing"),
        mid=("15", "CRP/2794/2026"),
        last=("27", "CRP/3015/2026"),
    ),
    ("tripura", "2026-10-12", "bench_1", "DAILY_MAIN_CAUSE_LIST_HON_BLE_JUSTICE_DR_T_AMARNATH_GOUD.pdf"): dict(
        parser="f2", count=14, date="2026-10-12", hall="2",
        first=("1", "WP(C)/733/2026"),
        mid=("8", "MAC App./94/2023"),
        last=("14", "LA.App./43/2026"),
    ),
    ("uttarakhand", "2026-10-12", "bench_1", "DAILY_CAUSE_LIST_Hon_ble_Mr_Justice_Manoj_Kumar_Tiwari_Hon_ble_Mr_Just.pdf"): dict(
        parser="f2", count=12, date="2026-10-12", hall="01",
        first=("1", "WPSB/406/2025"),
        mid=("7", "WPSB/661/2026"),
        last=("12", "WPMB/853/2026"),
    ),
}
