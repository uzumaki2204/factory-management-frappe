"""Apply UUID script naming and mandatory Device Name to existing sites."""

import frappe


def execute():
    from factory_management.install import ensure_device_schema

    ensure_device_schema()
    frappe.clear_cache(doctype="Factory Device")
