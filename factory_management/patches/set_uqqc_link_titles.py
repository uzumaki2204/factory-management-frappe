"""Use readable catalog codes and device names in UQQC event Link fields."""

import frappe


def execute():
    from factory_management.install import ensure_device_schema
    from factory_management.uqqc.provision import ensure_schema

    ensure_device_schema()
    ensure_schema()
    frappe.clear_cache()
