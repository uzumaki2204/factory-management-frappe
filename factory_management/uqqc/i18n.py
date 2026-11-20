"""Shared UTF-8 language catalog for UQQC browser and server messages."""

import json
from functools import lru_cache
from pathlib import Path

import frappe


@lru_cache(maxsize=1)
def catalog():
    path = Path(__file__).parents[1] / "public" / "uqqc" / "i18n.json"
    return json.loads(path.read_text(encoding="utf-8"))


def text(key, language=None):
    language = (language or getattr(frappe.local, "lang", None) or "vi").split("-")[0]
    values = catalog()
    return values.get(language, values["vi"]).get(key, values["en"].get(key, key))


def fail(key, permission=False):
    frappe.throw(text(key), frappe.PermissionError if permission else frappe.ValidationError)
