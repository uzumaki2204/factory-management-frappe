"""Add a read-only variant combinations section to the Product form."""

import frappe


DOCTYPE = "Product"
FIELDNAME = "variant_combinations"
FIELD_VALUES = {
    "label": "Variant Combinations",
    "fieldtype": "HTML",
    "hidden": 0,
}


def execute():
    if not frappe.db.exists("DocType", DOCTYPE):
        return

    field_values = dict(FIELD_VALUES)
    if frappe.db.exists("Custom Field", {"dt": DOCTYPE, "fieldname": "production_season"}) or frappe.db.exists(
        "DocField", {"parent": DOCTYPE, "fieldname": "production_season"}
    ):
        field_values["insert_after"] = "production_season"

    name = frappe.db.get_value("Custom Field", {"dt": DOCTYPE, "fieldname": FIELDNAME}, "name")
    if name:
        field = frappe.get_doc("Custom Field", name)
        changed = any(field.get(key) != value for key, value in field_values.items())
        if changed:
            field.update(field_values)
            field.save(ignore_permissions=True)
    else:
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": DOCTYPE,
            "fieldname": FIELDNAME,
            **field_values,
        }).insert(ignore_permissions=True)

    frappe.clear_cache(doctype=DOCTYPE)
