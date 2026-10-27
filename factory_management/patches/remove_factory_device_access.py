"""Remove the retired per-service Factory Device Access DocType."""

import frappe

from factory_management.device_registry import message


ACCESS_DOCTYPE = "Factory Device Access"


def _preflight():
    if frappe.db.exists("DocType", ACCESS_DOCTYPE):
        owner = frappe.db.get_value("DocType", ACCESS_DOCTYPE, ["custom", "module"], as_dict=True)
        if not owner or not owner.custom or owner.module != "Factory Management":
            frappe.throw(message("error.namespace_conflict"), frappe.ValidationError)

    for linked_type in ("DocField", "Custom Field"):
        if frappe.db.count(linked_type, {"options": ACCESS_DOCTYPE}):
            frappe.throw(
                message("error.device_access_referenced").format(doctype=ACCESS_DOCTYPE),
                frappe.ValidationError,
            )

    if frappe.db.exists("DocType", "Server Script") and frappe.db.count(
            "Server Script", {"script": ["like", f"%{ACCESS_DOCTYPE}%"]}):
        frappe.throw(
            message("error.device_access_referenced").format(doctype=ACCESS_DOCTYPE),
            frappe.ValidationError,
        )


def _update_uqqc_api_docs():
    from factory_management.uqqc.i18n import text

    old_description = "Requires X-UQQC-Token. The Factory Device must have UQQC access; its token is stored in Factory Device Client."
    new_description = text("docs.device", "en")
    for operation in ("uqqc_device_register", "uqqc_device_check"):
        name = frappe.db.get_value("API Documentation Endpoint", {"operation_id": operation}, "name")
        if not name:
            continue
        current = frappe.db.get_value("API Documentation Endpoint", name, "description")
        if current == old_description:
            frappe.db.set_value("API Documentation Endpoint", name, "description",
                                new_description, update_modified=False)


def execute():
    _preflight()
    if frappe.db.exists("DocType", ACCESS_DOCTYPE):
        frappe.delete_doc("DocType", ACCESS_DOCTYPE, ignore_permissions=True)
    if frappe.db.table_exists(ACCESS_DOCTYPE, cached=False):
        frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{ACCESS_DOCTYPE}`")
    _update_uqqc_api_docs()
    frappe.clear_cache()
