"""One-time DocType rename and Purchase Approval reference migration."""
import frappe

RENAMES = (("KTG Company", "Company"), ("KTG Department", "Department"))


def _replace(value):
    if not isinstance(value, str):
        return value
    for old, new in RENAMES:
        value = value.replace(old, new)
    return value


def _patch_field(doctype, field, filters=None):
    changed = 0
    for row in frappe.get_all(doctype, fields=["name", field], filters=filters or {}, limit_page_length=10000):
        value = row.get(field)
        replaced = _replace(value)
        if replaced != value:
            frappe.db.set_value(doctype, row.name, field, replaced, update_modified=False)
            changed += 1
    return changed


def run():
    renamed = []
    for old, new in RENAMES:
        if frappe.db.exists("DocType", old) and not frappe.db.exists("DocType", new):
            frappe.rename_doc("DocType", old, new, force=True)
            renamed.append(new)
    touched = {}
    fields = {
        "DocField": ["options"],
        "Custom Field": ["dt", "options"],
        "Property Setter": ["doc_type", "value"],
        "Server Script": ["reference_doctype", "script"],
        "Client Script": ["dt", "script"],
    }
    for doctype, columns in fields.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        for field in columns:
            if frappe.db.has_column(doctype, field):
                count = _patch_field(doctype, field)
                if count:
                    touched[doctype + "." + field] = count
    frappe.clear_cache()
    frappe.db.commit()
    return {"renamed": renamed, "updated": touched}
