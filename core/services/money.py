"""One way to write an amount of money, server side -- the same as the
frontend's formatINR: Indian digit grouping (1,31,000), and no ".00" for
whole rupees (paise only when there are some).

Emails use the rupee sign. PDFs use "Rs." -- fpdf2's core fonts are
Latin-1 and would print the rupee sign as "?".
"""

from __future__ import annotations

from decimal import Decimal


def _indian_grouping(digits: str) -> str:
    """ "13100000" -> "1,31,00,000": the last three digits, then pairs."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    pairs = []
    while len(head) > 2:
        pairs.insert(0, head[-2:])
        head = head[:-2]
    if head:
        pairs.insert(0, head)
    return ",".join(pairs) + "," + tail


def format_inr(amount, *, symbol: str = "₹") -> str:
    value = Decimal(str(amount))
    sign = "-" if value < 0 else ""
    value = abs(value).quantize(Decimal("0.01"))
    rupees, paise = divmod(value, 1)
    text = _indian_grouping(str(int(rupees)))
    if paise:
        text += f".{int(paise * 100):02d}"
    return f"{sign}{symbol}{text}"


def pdf_inr(amount) -> str:
    return format_inr(amount, symbol="Rs. ")
