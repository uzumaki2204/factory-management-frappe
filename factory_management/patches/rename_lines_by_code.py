"""Move line master DocTypes to KTG Master Data and rename lines by code."""

from collections import defaultdict

import frappe
from frappe.model.rename_doc import rename_doc

from factory_management.device_registry import message


DOCTYPE = "Production Line"
MAX_NAME_LENGTH = 140


def preview():
    """Return name collisions without changing records."""
    if not frappe.db.exists("DocType", DOCTYPE) or not frappe.db.table_exists(DOCTYPE):
        return {"count": 0, "rename_count": 0, "invalid": [], "duplicates": []}

    rows = frappe.get_all(DOCTYPE, fields=["name", "line_code"], limit_page_length=0)
    codes = defaultdict(list)
    invalid = []
    rename_count = 0
    for row in rows:
        code = row.line_code or ""
        if not code or code != code.strip() or len(code) > MAX_NAME_LENGTH:
            invalid.append(row.name)
            continue
        codes[code.casefold()].append(code)
        rename_count += row.name != code

    duplicates = sorted({values[0] for values in codes.values() if len(values) > 1}, key=str.casefold)
    return {"count": len(rows), "rename_count": rename_count,
            "invalid": sorted(invalid), "duplicates": duplicates}


def _validate():
    state = preview()
    if state["invalid"]:
        frappe.throw(message("error.line_code_invalid"), frappe.ValidationError)
    if state["duplicates"]:
        frappe.throw(message("error.line_code_duplicate").format(code=state["duplicates"][0]),
                     frappe.ValidationError)
    return state


def execute():
    state = _validate()
    if not state["count"] or not state["rename_count"]:
        return

    rows = frappe.get_all(DOCTYPE, fields=["name", "line_code"], order_by="name asc",
                          limit_page_length=0)
    pending = [(row.name, row.line_code) for row in rows if row.name != row.line_code]
    staged = []

    # Stage all changed names first so swaps and code-to-old-name collisions are safe.
    for old_name, code in pending:
        temp_name = "line-code-migration-" + frappe.generate_hash(length=24)
        while frappe.db.exists(DOCTYPE, temp_name):
            temp_name = "line-code-migration-" + frappe.generate_hash(length=24)
        rename_doc(DOCTYPE, old_name, temp_name, force=True, ignore_permissions=True,
                   show_alert=False, rebuild_search=False)
        staged.append((temp_name, code))

    for temp_name, code in staged:
        rename_doc(DOCTYPE, temp_name, code, force=True, ignore_permissions=True,
                   show_alert=False, rebuild_search=False)
