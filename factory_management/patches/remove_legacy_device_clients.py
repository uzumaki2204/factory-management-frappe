"""Remove obsolete client DocTypes after every credential reaches the shared registry."""

import frappe

from factory_management.device_registry import (
    CLIENT_TYPE, DEVICE_TYPE, credential_hash, message,
)


LEGACY_CLIENTS = (
    ("QC Device Client", "qc"),
    ("UQQC Device Client", "uqqc"),
)


def _fail(key, doctype):
    frappe.throw(message(key).format(doctype=doctype), frappe.ValidationError)


def _preflight():
    if not frappe.db.exists("DocType", DEVICE_TYPE) or not frappe.db.exists("DocType", CLIENT_TYPE):
        _fail("error.legacy_client_registry_missing", DEVICE_TYPE)

    for doctype, service_key in LEGACY_CLIENTS:
        meta = frappe.db.get_value("DocType", doctype, ["custom", "module"], as_dict=True)
        table_exists = frappe.db.table_exists(doctype, cached=False)
        if not meta and not table_exists:
            continue
        if meta and (not meta.custom or meta.module not in ("Quality Control", "UQQC")):
            _fail("error.legacy_client_namespace", doctype)
        if not table_exists:
            _fail("error.legacy_client_unmigrated", doctype)
        for linked_type in ("DocField", "Custom Field"):
            if frappe.db.count(linked_type, {"options": doctype}):
                _fail("error.legacy_client_referenced", doctype)
        if frappe.db.count("QC Legacy Map", {"target_doctype": doctype}):
            _fail("error.legacy_client_referenced", doctype)
        if frappe.db.count("Server Script", {"script": ["like", "%" + doctype + "%"]}):
            _fail("error.legacy_client_referenced", doctype)
        rows = frappe.db.sql(f"SELECT device, token_hash FROM `tab{doctype}`", as_dict=True)
        for row in rows:
            if not row.device or not row.token_hash:
                _fail("error.legacy_client_unmigrated", doctype)
            migrated = frappe.db.exists(CLIENT_TYPE, {
                "device": row.device,
                "service_key": service_key,
                "token_hash": credential_hash(service_key, legacy_hash=row.token_hash),
            })
            if not migrated:
                _fail("error.legacy_client_unmigrated", doctype)


def execute():
    _preflight()
    for doctype, _ in LEGACY_CLIENTS:
        if frappe.db.exists("DocType", doctype):
            frappe.delete_doc("DocType", doctype, ignore_permissions=True)
        if frappe.db.table_exists(doctype, cached=False):
            frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{doctype}`")
    frappe.clear_cache()
