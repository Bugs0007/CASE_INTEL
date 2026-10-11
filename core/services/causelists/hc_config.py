"""Per-High-Court data for the hcservices adapters.

Data, not logic: which benches exist, which of them hcservices actually
serves, which PDF layout parser reads that court's lists, and whether the
court is supported at all. Every `status="supported"` entry has a parser
that passes golden tests on the real fixtures under
core/tests/fixtures/causelists/hcservices_generic/; every other entry says
why it is not, in words the advocate sees.

Evidence for each entry: docs/causelists/COVERAGE.md (probed live
2026-10-10; counts and fixtures named there).
"""

from __future__ import annotations

from dataclasses import dataclass

SUPPORTED = "supported"
BLOCKED = "blocked"  # the source gives nothing usable
UNVERIFIED = "unverified"  # fetch works; no parser has passed golden tests

# Parser families (adapters/layouts/*)
PARSER_TELANGANA = "f1"  # the Telangana/Andhra coordinate parser
PARSER_TABLE = "f2"  # the adaptive item-column + case-column parser
PARSER_JK = "f3"
PARSER_DELHI = "f4"


@dataclass(frozen=True)
class Bench:
    code: str
    name: str
    served: bool = True  # False: the index lists rows whose PDFs are not served


@dataclass(frozen=True)
class HCConfig:
    code: str  # bharat_courts court code
    name: str
    state_code: str
    benches: tuple[Bench, ...]
    status: str
    parser: str = ""
    reason: str = ""  # shown to the advocate when not supported
    # Benches hcservices answered "No cause List Available" for on both probe
    # dates; skipped when the case's bench is unknown (otherwise their
    # emptiness would stop a complete read forever).
    skip_when_bench_unknown: tuple[str, ...] = ()

    def bench(self, code: str) -> Bench | None:
        return next((b for b in self.benches if b.code == code), None)

    @property
    def served_benches(self) -> tuple[Bench, ...]:
        return tuple(b for b in self.benches if b.served)


_NOT_UPLOADED = (
    "hcservices lists this court's cause lists but serves no PDFs for them "
    "(every link answers 'Order not uploaded'); check the court's own site"
)
_NO_LIST = "hcservices has no cause list for this court; check the court's own site"


def _b(*pairs, unserved=()):
    return tuple(Bench(code, name, served=code not in unserved) for code, name in pairs)


_CONFIGS = [
    HCConfig("allahabad", "Allahabad High Court", "13",
             _b(("1", "Allahabad"), ("2", "Lucknow"), unserved=("1", "2")), BLOCKED, reason=_NOT_UPLOADED),
    HCConfig("andhra", "Andhra Pradesh High Court", "2", _b(("1", "Principal Bench")), SUPPORTED, PARSER_TELANGANA),
    HCConfig("bombay", "Bombay High Court", "1",
             _b(("1", "Appellate Side"), ("2", "Original Side"), ("3", "Aurangabad"),
                ("4", "Nagpur"), ("5", "Goa"), ("7", "Kolhapur"), ("6", "Special Court (TORTS)")),
             SUPPORTED, PARSER_TABLE, skip_when_bench_unknown=("6",)),
    HCConfig("calcutta", "Calcutta High Court", "16",
             _b(("1", "Original Side"), ("3", "Appellate Side"), ("2", "Circuit Bench at Jalpaiguri"),
                ("4", "Circuit Bench at Port Blair")), SUPPORTED, PARSER_TABLE),
    HCConfig("chhattisgarh", "Chhattisgarh High Court", "18", _b(("1", "Principal Bench")), SUPPORTED, PARSER_TABLE),
    HCConfig("delhi", "Delhi High Court", "26", _b(("1", "Principal Bench")), SUPPORTED, PARSER_DELHI),
    HCConfig("gauhati", "Gauhati High Court", "6",
             _b(("1", "Principal Seat at Guwahati"), ("2", "Kohima"), ("3", "Aizawl"), ("4", "Itanagar")),
             SUPPORTED, PARSER_TABLE),
    HCConfig("gujarat", "Gujarat High Court", "17", _b(("1", "Gujarat High Court"), unserved=("1",)),
             BLOCKED, reason=_NOT_UPLOADED),
    HCConfig("himachal", "Himachal Pradesh High Court", "5", _b(("1", "Himachal Pradesh High Court"), unserved=("1",)),
             BLOCKED, reason=_NOT_UPLOADED),
    HCConfig("jammu", "Jammu & Kashmir and Ladakh High Court", "12", _b(("1", "Jammu"), ("2", "Srinagar")),
             SUPPORTED, PARSER_JK),
    HCConfig("jharkhand", "Jharkhand High Court", "7", _b(("1", "Principal Bench"), unserved=("1",)),
             BLOCKED, reason=_NOT_UPLOADED),
    HCConfig("karnataka", "Karnataka High Court", "3",
             _b(("1", "Bengaluru"), ("2", "Dharwad"), ("3", "Kalaburagi")), SUPPORTED, PARSER_TABLE),
    HCConfig("kerala", "Kerala High Court", "4", _b(("1", "High Court of Kerala"), unserved=("1",)),
             BLOCKED, reason=_NOT_UPLOADED),
    HCConfig("mp", "Madhya Pradesh High Court", "23",
             _b(("1", "Jabalpur"), ("2", "Indore"), ("3", "Gwalior"), unserved=("1", "2", "3")),
             BLOCKED, reason=_NO_LIST),
    HCConfig("madras", "Madras High Court", "10",
             _b(("1", "Principal Bench"), ("2", "Madurai Bench"), unserved=("2",)), SUPPORTED, PARSER_TABLE),
    HCConfig("manipur", "Manipur High Court", "25", _b(("1", "High Court of Manipur")), SUPPORTED, PARSER_TABLE),
    HCConfig("meghalaya", "Meghalaya High Court", "21", _b(("1", "High Court of Meghalaya")), SUPPORTED, PARSER_TABLE),
    HCConfig("orissa", "Orissa High Court", "11", _b(("1", "High Court of Orissa")), SUPPORTED, PARSER_TABLE),
    HCConfig("patna", "Patna High Court", "8", _b(("1", "Principal Bench")), SUPPORTED, PARSER_TABLE),
    HCConfig("punjab", "Punjab and Haryana High Court", "22", _b(("1", "High Court of Punjab and Haryana"), unserved=("1",)),
             BLOCKED, reason=_NO_LIST),
    HCConfig("rajasthan", "Rajasthan High Court", "9", _b(("1", "Jaipur"), ("2", "Jodhpur")), SUPPORTED, PARSER_TABLE),
    HCConfig("sikkim", "Sikkim High Court", "24", _b(("1", "High Court of Sikkim")), SUPPORTED, PARSER_TABLE),
    HCConfig("tripura", "Tripura High Court", "20", _b(("1", "High Court of Tripura")), SUPPORTED, PARSER_TABLE),
    HCConfig("uttarakhand", "Uttarakhand High Court", "15", _b(("1", "High Court of Uttarakhand")), SUPPORTED, PARSER_TABLE),
]

HC_CONFIGS: dict[str, HCConfig] = {c.code: c for c in _CONFIGS}

# bharat_courts registers some benches as their own "court" codes
# ('bombay-nagpur'); the portal addresses them as bench codes of the parent.
BENCH_VARIANTS: dict[str, tuple[str, str]] = {
    "allahabad-lucknow": ("allahabad", "2"),
    "bombay-nagpur": ("bombay", "4"),
    "bombay-aurangabad": ("bombay", "3"),
    "bombay-goa": ("bombay", "5"),
}


def config_for(hc_code: str) -> HCConfig | None:
    return HC_CONFIGS.get(hc_code)
