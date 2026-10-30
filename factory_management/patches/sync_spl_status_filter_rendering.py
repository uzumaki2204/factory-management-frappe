"""Sync the visible label for SPL status filters on existing sites."""

import frappe


def execute():
    from factory_management.install import ensure_doctype
    from factory_management.spl_po.schema import SETTINGS

    ensure_doctype("SPL Import Settings", SETTINGS, module="Factory Management")
    frappe.clear_cache(doctype="SPL Import Settings")
