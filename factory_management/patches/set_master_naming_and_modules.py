"""Use code-based names and place shared masters in KTG Master Data."""

import frappe

from factory_management.device_registry import message
from factory_management.install import ensure_module


DOCTYPE_SETTINGS = {
    "QC Defect": {"fieldname": "code", "module": "Quality Control"},
    "Factory": {"fieldname": "factory_code", "module": "KTG Master Data"},
    "Product Color": {"fieldname": "color_code", "module": "KTG Master Data"},
    "Production Season": {"fieldname": "season_code", "module": "KTG Master Data"},
    "ProductSize": {"fieldname": "size_label", "module": "KTG Master Data"},
    "Line Group": {"fieldname": "group_code", "module": "KTG Master Data"},
}


def execute():
    ensure_module()
    for doctype, settings in DOCTYPE_SETTINGS.items():
        if not frappe.db.exists("DocType", doctype):
            frappe.throw(
                message("error.naming_doctype_missing").format(doctype=doctype),
                frappe.ValidationError,
            )

        doc = frappe.get_doc("DocType", doctype)
        fieldname = settings["fieldname"]
        if not any(field.fieldname == fieldname for field in doc.fields):
            frappe.throw(
                message("error.naming_code_field_missing").format(
                    doctype=doctype, field=fieldname,
                ),
                frappe.ValidationError,
            )

        values = {
            "module": settings["module"],
            "naming_rule": "By fieldname",
            "autoname": "field:" + fieldname,
            "allow_rename": 1,
        }
        if any(doc.get(key) != value for key, value in values.items()):
            doc.update(values)
            doc.save(ignore_permissions=True)
    frappe.clear_cache()
