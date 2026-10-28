"""Rename the app-owned Size DocType while preserving existing record names.

This forward-only patch uses Frappe's DocType rename so Link fields and the
underlying table are migrated together. Existing size names remain unchanged.
"""

import re

import frappe
from frappe.model.rename_doc import rename_doc

from factory_management.device_registry import message
from factory_management.install import ensure_module


OLD_DOCTYPE = "Size"
NEW_DOCTYPE = "ProductSize"
MASTER_DATA_MODULE = "KTG Master Data"
ALLOWED_OLD_MODULES = {MASTER_DATA_MODULE, "Quality Control", "Factory Management"}
MAX_LABEL_LENGTH = 140
SERVER_SCRIPT_TABLE_PATTERN = re.compile(r"(?<![A-Za-z0-9_])tabSize(?![A-Za-z0-9_])")


def _validate_existing_labels():
    if not frappe.db.table_exists(OLD_DOCTYPE):
        return

    seen = {}
    rows = frappe.get_all(
        OLD_DOCTYPE,
        fields=["name", "size_label"],
        limit_page_length=0,
    )
    for row in rows:
        label = row.size_label or ""
        if not label or label != label.strip() or len(label) > MAX_LABEL_LENGTH:
            frappe.throw(message("error.product_size_label_invalid"), frappe.ValidationError)

        normalized = label.casefold()
        if normalized in seen:
            frappe.throw(
                message("error.product_size_label_duplicate").format(label=label),
                frappe.ValidationError,
            )
        seen[normalized] = row.name


def _update_legacy_maps():
    doctype = "QC Legacy Map"
    if not frappe.db.table_exists(doctype) or not frappe.db.has_column(doctype, "target_doctype"):
        return

    frappe.db.sql(
        "UPDATE `tabQC Legacy Map` SET `target_doctype` = %s WHERE `target_doctype` = %s",
        (NEW_DOCTYPE, OLD_DOCTYPE),
    )


def _update_server_scripts():
    if not frappe.db.exists("DocType", "Server Script"):
        return

    for row in frappe.get_all("Server Script", fields=["name", "script"], limit_page_length=0):
        script = row.script or ""
        updated = SERVER_SCRIPT_TABLE_PATTERN.sub("tabProductSize", script)
        if updated != script:
            frappe.db.set_value(
                "Server Script", row.name, "script", updated, update_modified=False,
            )


def execute():
    old_exists = bool(frappe.db.exists("DocType", OLD_DOCTYPE))
    new_exists = bool(frappe.db.exists("DocType", NEW_DOCTYPE))

    if old_exists and new_exists:
        frappe.throw(message("error.product_size_rename_conflict"), frappe.ValidationError)
    if not old_exists and not new_exists:
        # Fresh installs create ProductSize from its metadata snapshot later in migrate.
        return

    if old_exists:
        old_module = frappe.db.get_value("DocType", OLD_DOCTYPE, "module")
        if old_module not in ALLOWED_OLD_MODULES:
            frappe.throw(message("error.product_size_namespace_conflict"), frappe.ValidationError)
        _validate_existing_labels()
    else:
        new_module = frappe.db.get_value("DocType", NEW_DOCTYPE, "module")
        if new_module != MASTER_DATA_MODULE:
            frappe.throw(message("error.product_size_namespace_conflict"), frappe.ValidationError)

    ensure_module()

    if old_exists:
        rename_doc(
            "DocType", OLD_DOCTYPE, NEW_DOCTYPE,
            force=True, ignore_permissions=True, show_alert=False, rebuild_search=False,
        )

    frappe.db.set_value(
        "DocType", NEW_DOCTYPE, "module", MASTER_DATA_MODULE, update_modified=False,
    )
    _update_legacy_maps()
    _update_server_scripts()
    frappe.clear_cache()
