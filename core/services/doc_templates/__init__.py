"""Template-merge document generation (vakalatnama, memo of appearance,
letterhead cover letter). See engine.py."""

from .engine import (
    DocTemplateError,
    InvalidContactError,
    MissingFieldsError,
    UnknownTemplateError,
    generate_document,
    get_template,
    list_templates,
    pick_contact,
    resolve,
)

__all__ = [
    "DocTemplateError",
    "InvalidContactError",
    "MissingFieldsError",
    "UnknownTemplateError",
    "generate_document",
    "get_template",
    "list_templates",
    "pick_contact",
    "resolve",
]
