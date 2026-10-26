"""Validation shared by the unified QC and UQQC defect catalogs."""

import frappe

from factory_management.uqqc.i18n import text


def _validate(doc, group_type, item_type, parent_field):
    record_type = doc.get("record_type")
    if record_type == group_type:
        if doc.get(parent_field):
            frappe.throw(text("catalog.group_cannot_have_parent"), frappe.ValidationError)
        return
    if record_type != item_type:
        frappe.throw(text("catalog.invalid_record_type"), frappe.ValidationError)
    parent = doc.get(parent_field)
    if not parent:
        frappe.throw(text("catalog.parent_required"), frappe.ValidationError)
    parent_type = frappe.db.get_value(doc.doctype, parent, "record_type")
    if parent_type != group_type:
        frappe.throw(text("catalog.parent_must_be_group"), frappe.ValidationError)


def validate_qc_defect(doc, method=None):
    _validate(doc, "Group", "Defect", "defect_group")


def validate_qc_position(doc, method=None):
    _validate(doc, "Group", "Position", "position_group")


def validate_uqqc_defect(doc, method=None):
    _validate(doc, "Group", "Defect", "defect_group")


def validate_uqqc_position(doc, method=None):
    _validate(doc, "Group", "Position", "position_group")
