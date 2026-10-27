"""Remove obsolete pairing and client details from Factory Device."""

import frappe

from factory_management import __version__
from factory_management.device_registry import (
    CLIENT_TYPE, DEVICE_TYPE, credential_hash, message,
)
from factory_management.install import ensure_schema


LEGACY_FIELDS = (
    "pairing_status",
    "token_hash",
    "pending_token_hash",
    "browser_name",
    "operating_system",
)
TOKEN_FIELDS = ("token_hash", "pending_token_hash")


def _columns():
    if not frappe.db.table_exists(DEVICE_TYPE, cached=False):
        return set()
    return set(frappe.db.get_table_columns(DEVICE_TYPE))


def _legacy_token_rows(columns=None):
    columns = columns if columns is not None else _columns()
    fields = [field for field in TOKEN_FIELDS if field in columns]
    if not fields:
        return []
    selected = ["name", *fields]
    return frappe.db.sql(
        "SELECT " + ", ".join(f"`{field}`" for field in selected)
        + f" FROM `tab{DEVICE_TYPE}`",
        as_dict=True,
    )


def _unmigrated_tokens(columns=None):
    columns = columns if columns is not None else _columns()
    if not any(field in columns for field in TOKEN_FIELDS):
        return []

    if not frappe.db.table_exists(CLIENT_TYPE, cached=False):
        return [row for row in _legacy_token_rows(columns)
                for field in TOKEN_FIELDS if row.get(field)]

    missing = []
    for row in _legacy_token_rows(columns):
        for field in TOKEN_FIELDS:
            legacy_hash = row.get(field)
            if not legacy_hash:
                continue
            migrated = frappe.db.exists(CLIENT_TYPE, {
                "device": row.name,
                "service_key": "qc",
                "token_hash": credential_hash("qc", legacy_hash=legacy_hash),
            })
            if not migrated:
                missing.append((row.name, field))
    return missing


def status():
    """Read-only preflight and post-migration state for the selected site."""
    fields = set()
    if frappe.db.exists("DocType", DEVICE_TYPE):
        fields = {row.fieldname for row in frappe.get_meta(DEVICE_TYPE).fields}
    custom_fields = set(frappe.get_all(
        "Custom Field", filters={"dt": DEVICE_TYPE}, pluck="fieldname",
    )) if frappe.db.exists("DocType", "Custom Field") else set()
    property_setters = frappe.get_all(
        "Property Setter",
        filters={"doc_type": DEVICE_TYPE, "field_name": ["in", LEGACY_FIELDS]},
        pluck="name",
    ) if frappe.db.exists("DocType", "Property Setter") else []
    return {
        "app_version": __version__,
        "legacy_doc_fields": sorted(fields.intersection(LEGACY_FIELDS)),
        "legacy_custom_fields": sorted(custom_fields.intersection(LEGACY_FIELDS)),
        "legacy_property_setters": property_setters,
        "legacy_columns": sorted(_columns().intersection(LEGACY_FIELDS)),
        "unmigrated_token_count": len(_unmigrated_tokens()),
    }


def _delete_legacy_metadata():
    for row in frappe.get_all(
            "Property Setter",
            filters={"doc_type": DEVICE_TYPE, "field_name": ["in", LEGACY_FIELDS]},
            pluck="name"):
        frappe.delete_doc("Property Setter", row, ignore_permissions=True)
    for row in frappe.get_all(
            "Custom Field",
            filters={"dt": DEVICE_TYPE, "fieldname": ["in", LEGACY_FIELDS]},
            pluck="name"):
        frappe.delete_doc("Custom Field", row, ignore_permissions=True)


def execute():
    if not frappe.db.exists("DocType", DEVICE_TYPE):
        return

    columns = _columns()
    unmigrated = _unmigrated_tokens(columns)
    if unmigrated:
        frappe.throw(
            message("error.legacy_device_token_unmigrated").format(count=len(unmigrated)),
            frappe.ValidationError,
        )

    _delete_legacy_metadata()
    ensure_schema()

    for field in _columns().intersection(LEGACY_FIELDS):
        frappe.db.sql_ddl(f"ALTER TABLE `tab{DEVICE_TYPE}` DROP COLUMN `{field}`")
    frappe.clear_cache(doctype=DEVICE_TYPE)
    frappe.clear_cache()
