"""Helpers shared by the fpdf2 renderers (invoices, hearing prep sheets,
client statements, generated documents)."""


def pdf_safe(text) -> str:
    """Make `text` renderable by fpdf2's built-in (core) fonts.

    Those fonts are Latin-1 only and raise on anything outside it. Indian
    party names routinely carry characters that aren't (curly quotes,
    en-dashes, Devanagari). Substituting '?' instead of raising keeps a
    rendering detail from failing the whole document.
    """
    if text is None:
        return ""
    return str(text).encode("latin-1", "replace").decode("latin-1")


def draw_letterhead(pdf, profile) -> None:
    """The advocate's letterhead block and rule, at the current position.

    Shared so an invoice, a statement and a cover letter carry the same
    header: letterhead name, address lines, bar registration number.
    """
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, pdf_safe(profile.letterhead_name or "Advocate"), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    for line in (profile.address or "").splitlines():
        if line.strip():
            pdf.cell(0, 5, pdf_safe(line.strip()), new_x="LMARGIN", new_y="NEXT")
    if profile.bar_registration_number:
        pdf.cell(
            0,
            5,
            pdf_safe(f"Enrolment No.: {profile.bar_registration_number}"),
            new_x="LMARGIN",
            new_y="NEXT",
        )

    pdf.ln(4)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(6)
