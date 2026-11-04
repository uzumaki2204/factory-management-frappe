"""Move the Product variant combinations HTML field into the DocType schema."""

import frappe


DOCTYPE = "Product"
FIELDNAME = "variant_combinations"


def execute():
    if not frappe.db.exists("DocType", DOCTYPE):
        return

    name = frappe.db.get_value("Custom Field", {"dt": DOCTYPE, "fieldname": FIELDNAME}, "name")
    if not name:
        return

    custom_field = frappe.get_doc("Custom Field", name)
    if custom_field.fieldtype != "HTML":
        frappe.throw(
            frappe._("The Product variant combinations field has an unexpected type."),
            frappe.ValidationError,
        )

    frappe.delete_doc("Custom Field", name, ignore_permissions=True)
    frappe.clear_cache(doctype=DOCTYPE)
