"""Make Assignment UID generated and read-only on existing sites."""

import frappe

from factory_management.install import MASTER_TYPE_MODULES, MASTER_TYPES, ensure_doctype


def execute():
    doctype = "Line Group Assignment"
    ensure_doctype(doctype, MASTER_TYPES[doctype], module=MASTER_TYPE_MODULES[doctype])
    frappe.clear_cache(doctype=doctype)
