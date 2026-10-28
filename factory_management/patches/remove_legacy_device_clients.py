"""Remove obsolete QC/UQQC client DocTypes during older upgrade paths."""

import frappe

from factory_management.device_registry import (
    DEVICE_TYPE, message,
)


LEGACY_CLIENTS = (
    ("QC Device Client", "qc"),
    ("UQQC Device Client", "uqqc"),
)


def _fail(key, doctype):
    frappe.throw(message(key).format(doctype=doctype), frappe.ValidationError)


def _preflight():
    if not frappe.db.exists("DocType", DEVICE_TYPE):
        _fail("error.legacy_client_registry_missing", DEVICE_TYPE)

    for doctype, _ in LEGACY_CLIENTS:
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
        # These service tokens are discarded by the ID-only device migration.


def execute():
    _preflight()
    for doctype, _ in LEGACY_CLIENTS:
        if frappe.db.exists("DocType", doctype):
            frappe.delete_doc("DocType", doctype, ignore_permissions=True)
        if frappe.db.table_exists(doctype, cached=False):
            frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{doctype}`")
    frappe.clear_cache()
