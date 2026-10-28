"""Retire the duplicated device identifiers and browser credentials."""

import uuid

import frappe

from factory_management.device_registry import CLIENT_TYPE, DEVICE_TYPE, message
from factory_management.install import ensure_device_schema


IDENTITY_FIELDS = ("device_id", "device_uid")


def _columns():
    if not frappe.db.table_exists(DEVICE_TYPE, cached=False):
        return set()
    return set(frappe.db.get_table_columns(DEVICE_TYPE))


def _preflight():
    if not frappe.db.exists("DocType", DEVICE_TYPE):
        return
    columns = _columns()
    selected = ["name"] + (["device_id"] if "device_id" in columns else [])
    for row in frappe.db.sql(
        "SELECT " + ", ".join(f"`{field}`" for field in selected)
        + f" FROM `tab{DEVICE_TYPE}`", as_dict=True,
    ):
        try:
            valid_uuid = str(uuid.UUID(str(row.name))) == str(row.name).lower()
        except (TypeError, ValueError):
            valid_uuid = False
        if not valid_uuid or ("device_id" in columns and row.device_id != row.name):
            frappe.throw(message("error.device_id_name_mismatch").format(device=row.name),
                         frappe.ValidationError)

    if frappe.db.exists("DocType", CLIENT_TYPE):
        for field_type in ("DocField", "Custom Field"):
            if frappe.db.count(field_type, {"options": CLIENT_TYPE}):
                frappe.throw(message("error.device_client_referenced"), frappe.ValidationError)
        if frappe.db.exists("DocType", "QC Legacy Map") and frappe.db.count(
                "QC Legacy Map", {"target_doctype": CLIENT_TYPE}):
            frappe.throw(message("error.device_client_referenced"), frappe.ValidationError)
        if frappe.db.count("Server Script", {"script": ["like", "%" + CLIENT_TYPE + "%"]}):
            frappe.throw(message("error.device_client_referenced"), frappe.ValidationError)


def _remove_identity_metadata():
    for row in frappe.get_all("Property Setter", filters={
            "doc_type": DEVICE_TYPE, "field_name": ["in", IDENTITY_FIELDS]}, pluck="name"):
        frappe.delete_doc("Property Setter", row, ignore_permissions=True)
    for row in frappe.get_all("Custom Field", filters={
            "dt": DEVICE_TYPE, "fieldname": ["in", IDENTITY_FIELDS]}, pluck="name"):
        frappe.delete_doc("Custom Field", row, ignore_permissions=True)


def execute():
    if not frappe.db.exists("DocType", DEVICE_TYPE):
        return
    _preflight()
    _remove_identity_metadata()
    ensure_device_schema()
    if frappe.db.exists("DocType", CLIENT_TYPE):
        frappe.db.delete(CLIENT_TYPE)
        frappe.delete_doc("DocType", CLIENT_TYPE, ignore_permissions=True)
    if frappe.db.table_exists(CLIENT_TYPE, cached=False):
        frappe.db.sql_ddl(f"DROP TABLE `tab{CLIENT_TYPE}`")
    for field in _columns().intersection(IDENTITY_FIELDS):
        frappe.db.sql_ddl(f"ALTER TABLE `tab{DEVICE_TYPE}` DROP COLUMN `{field}`")
    frappe.clear_cache(doctype=DEVICE_TYPE)
    frappe.clear_cache()
