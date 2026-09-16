"""Helpers shared by the fpdf2 renderers (invoices, hearing prep sheets)."""


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
