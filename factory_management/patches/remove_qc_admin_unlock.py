"""Remove the retired QC admin unlock setting and add the per-page lock gate."""

import re
from pathlib import Path

import frappe
from frappe.utils.password import remove_encrypted_password


SETTINGS_DOCTYPE = "QC Settings"
LOCK_DIALOG_ID = 'id="page-lock-dialog"'


def _remove_admin_unlock_setting():
    if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
        return

    remove_encrypted_password(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE, "admin_unlock_code")
    frappe.db.delete("Singles", {"doctype": SETTINGS_DOCTYPE, "field": "admin_unlock_code"})
    frappe.db.delete("DocField", {"parent": SETTINGS_DOCTYPE, "fieldname": "admin_unlock_code"})

    for row in frappe.get_all(
        "Custom Field", filters={"dt": SETTINGS_DOCTYPE, "fieldname": "admin_unlock_code"}, fields=["name"]
    ):
        frappe.delete_doc("Custom Field", row.name, ignore_permissions=True)

    remaining_docfields = frappe.db.count("DocField", {"parent": SETTINGS_DOCTYPE})
    remaining_custom_fields = frappe.db.count("Custom Field", {"dt": SETTINGS_DOCTYPE})
    meta = frappe.get_doc("DocType", SETTINGS_DOCTYPE)
    if not remaining_docfields and not remaining_custom_fields and meta.custom and meta.module == "Quality Control":
        frappe.delete_doc("DocType", SETTINGS_DOCTYPE, force=True, ignore_permissions=True)


def _lock_dialog_html():
    source = Path(__file__).resolve().parents[1] / "web_pages" / "qc.html"
    content = source.read_text(encoding="utf-8")
    start = content.find("<dialog " + LOCK_DIALOG_ID)
    end = content.find("</dialog>", start)
    if start < 0 or end < 0:
        return ""
    return content[start:end + len("</dialog>")]


def _update_qc_page():
    page_name = frappe.db.get_value("Web Page", {"route": "qc"}, "name")
    if not page_name:
        return

    page = frappe.get_doc("Web Page", page_name)
    content = page.main_section_html or ""
    lock_dialog = _lock_dialog_html()
    if not lock_dialog:
        return

    content = re.sub(
        r'\s*<div id="unlock-panel"[^>]*>[\s\S]*?</div>\s*</div>\s*</div>',
        "",
        content,
        count=1,
    )
    if LOCK_DIALOG_ID not in content:
        toast_index = content.find('<div id="qc-toast"')
        if toast_index >= 0:
            app_close = content.rfind("</div>", 0, toast_index)
            if app_close >= 0:
                insertion = app_close + len("</div>")
                content = content[:insertion] + "\n" + lock_dialog + "\n" + content[insertion:]
            else:
                content += "\n" + lock_dialog
        else:
            content += "\n" + lock_dialog

    if content != page.main_section_html:
        page.main_section_html = content
        page.save(ignore_permissions=True)


def _deactivate_retired_api_docs():
    if not frappe.db.exists("DocType", "API Documentation Endpoint"):
        return
    rows = frappe.get_all(
        "API Documentation Endpoint", fields=["name", "path", "operation_id"], limit_page_length=0
    )
    for row in rows:
        if "disable_client_lock" in (row.path or "") or row.operation_id == "disableClientLock":
            frappe.db.set_value("API Documentation Endpoint", row.name, "is_active", 0, update_modified=False)


def execute():
    _remove_admin_unlock_setting()
    _update_qc_page()
    _deactivate_retired_api_docs()
    frappe.clear_cache()
