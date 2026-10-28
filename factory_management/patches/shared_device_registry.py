"""Move legacy QC identity and links to the shared Factory Device DocType."""

import frappe

from factory_management.device_registry import (
    DEVICE_TYPE, message,
)
from factory_management.install import ensure_device_schema, ensure_module


def _preflight():
    if not frappe.db.exists("DocType", "QC Device"):
        return
    if frappe.db.exists("DocType", DEVICE_TYPE):
        frappe.throw(message("error.target_exists"), frappe.ValidationError)


def _replace_link_options():
    for meta_type in ("DocField", "Custom Field"):
        for row in frappe.get_all(meta_type, filters={"options": "QC Device"},
                                  fields=["name"], limit_page_length=0):
            frappe.db.set_value(meta_type, row.name, "options", DEVICE_TYPE, update_modified=False)
    for row in frappe.get_all("QC Legacy Map", filters={"target_doctype": "QC Device"},
                              fields=["name"], limit_page_length=0):
        frappe.db.set_value("QC Legacy Map", row.name, "target_doctype", DEVICE_TYPE,
                            update_modified=False)
    for row in frappe.get_all("Server Script", fields=["name", "script"], limit_page_length=0):
        script = row.script or ""
        updated = script.replace("tabQC Device", "tabFactory Device")
        if updated != script:
            frappe.db.set_value("Server Script", row.name, "script", updated,
                                update_modified=False)


def _legacy_rows(doctype):
    if not frappe.db.exists("DocType", doctype):
        return []
    fields = ["device", "status", "token_hash", "browser_name", "operating_system"]
    if frappe.db.has_column(doctype, "last_seen_at"):
        fields.append("last_seen_at")
    return frappe.get_all(doctype, fields=fields, limit_page_length=0)


def _update_api_docs():
    from factory_management.uqqc.i18n import text

    old = text("docs.device_legacy", "en")
    new = text("docs.device", "en")
    for row in frappe.get_all("API Documentation Endpoint",
                              filters={"description": old}, fields=["name"], limit_page_length=0):
        frappe.db.set_value("API Documentation Endpoint", row.name, "description", new,
                            update_modified=False)


def _retire_master_pairing_fields():
    columns = set(frappe.db.get_table_columns(DEVICE_TYPE))
    token_fields = [field for field in ("token_hash", "pending_token_hash")
                    if field in columns]
    if not token_fields:
        return
    assignments = ", ".join(f"`{field}` = NULL" for field in token_fields)
    frappe.db.sql(f"UPDATE `tab{DEVICE_TYPE}` SET {assignments}")
    for fieldname in ("pairing_status", "token_hash", "pending_token_hash"):
        field_name = frappe.db.get_value("DocField", {"parent": DEVICE_TYPE,
                                                       "fieldname": fieldname}, "name")
        if field_name:
            frappe.db.set_value("DocField", field_name,
                                {"hidden": 1, "in_list_view": 0, "read_only": 1},
                                update_modified=False)


def execute():
    _preflight()
    ensure_module()
    renamed = frappe.db.exists("DocType", "QC Device")
    if renamed:
        frappe.rename_doc("DocType", "QC Device", DEVICE_TYPE, force=True)
        frappe.db.set_value("DocType", DEVICE_TYPE, "module", "Factory Management")
    from factory_management.patches.use_factory_device_record_id import _preflight
    _preflight()
    ensure_device_schema()
    _replace_link_options()
    # Browser credentials are intentionally retired by the later ID-only patch.
    _retire_master_pairing_fields()
    _update_api_docs()
    frappe.clear_cache()
