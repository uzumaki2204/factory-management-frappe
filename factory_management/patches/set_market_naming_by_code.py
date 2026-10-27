"""Apply Market's code-based naming rule to the site's DocType metadata."""

import frappe

from factory_management.device_registry import message


def execute():
    if not frappe.db.exists("DocType", "Market"):
        frappe.throw(message("error.market_doctype_missing"), frappe.ValidationError)

    market = frappe.get_doc("DocType", "Market")
    if not any(field.fieldname == "code" for field in market.fields):
        frappe.throw(message("error.market_code_field_missing"), frappe.ValidationError)

    if market.naming_rule == "By fieldname" and market.autoname == "field:code":
        return

    market.naming_rule = "By fieldname"
    market.autoname = "field:code"
    market.save(ignore_permissions=True)
    frappe.clear_cache(doctype="Market")
