"""Move QC and UQQC identities and credentials to the shared device registry.

This patch is intentionally repeatable. A follow-up patch removes the legacy
client DocTypes after verifying the shared client registry.
"""

import frappe

from factory_management.device_registry import (
    CLIENT_TYPE, DEVICE_TYPE, credential_hash,
    import_legacy_client, message,
)
from factory_management.install import ensure_device_schema, ensure_module


def _preflight():
    if not frappe.db.exists("DocType", "QC Device"):
        return
    if frappe.db.exists("DocType", DEVICE_TYPE):
        frappe.throw(message("error.target_exists"), frappe.ValidationError)
    seen = {}
    for row in frappe.get_all("QC Device", fields=["name", "device_uid"], limit_page_length=0):
        uid = (row.device_uid or "").strip().casefold()
        if not uid or (uid in seen and seen[uid] != row.name):
            frappe.throw(message("error.duplicate_uid"), frappe.ValidationError)
        seen[uid] = row.name


def _replace_link_options():
    for meta_type in ("DocField", "Custom Field"):
        for row in frappe.get_all(meta_type, filters={"options": "QC Device"},
                                  fields=["name"], limit_page_length=0):
            frappe.db.set_value(meta_type, row.name, "options", DEVICE_TYPE, update_modified=False)
    for row in frappe.get_all("QC Legacy Map", filters={"target_doctype": "QC Device"},
                              fields=["name"], limit_page_length=0):
        frappe.db.set_value("QC Legacy Map", row.name, "target_doctype", DEVICE_TYPE,
                            update_modified=False)
    for row in frappe.get_all("Server Script", fields=["name", "script"], limit_page_length=0):
        script = row.script or ""
        updated = script.replace("tabQC Device", "tabFactory Device")
        if updated != script:
            frappe.db.set_value("Server Script", row.name, "script", updated,
                                update_modified=False)


def _legacy_rows(doctype):
    if not frappe.db.exists("DocType", doctype):
        return []
    fields = ["device", "status", "token_hash", "browser_name", "operating_system"]
    if frappe.db.has_column(doctype, "last_seen_at"):
        fields.append("last_seen_at")
    return frappe.get_all(doctype, fields=fields, limit_page_length=0)


def _migrate_credentials():
    credentials = {}
    priority = {"Approved": 0, "Pending": 1, "Rejected": 2, "Revoked": 3}

    def collect(device_name, service, legacy_hash, status, browser_name=None,
                operating_system=None, last_seen_at=None):
        if not legacy_hash:
            return
        key = (service, legacy_hash)
        existing = credentials.get(key)
        if existing and existing[0] != device_name:
            frappe.throw(message("error.token_bound"), frappe.ValidationError)
        if not existing or priority.get(status, 1) > priority.get(existing[3], 1):
            credentials[key] = (device_name, service, legacy_hash, status,
                                browser_name, operating_system, last_seen_at)

    for doctype, service in (("QC Device Client", "qc"), ("UQQC Device Client", "uqqc")):
        for row in _legacy_rows(doctype):
            collect(row.device, service, row.token_hash, row.status,
                    row.browser_name, row.operating_system, row.get("last_seen_at"))

    device_columns = set(frappe.db.get_table_columns(DEVICE_TYPE))
    legacy_fields = ["name"] + [field for field in (
        "token_hash", "pending_token_hash", "pairing_status", "last_seen_at",
    ) if field in device_columns]
    if "token_hash" in device_columns or "pending_token_hash" in device_columns:
        for device in frappe.db.sql(
                "SELECT " + ", ".join(f"`{field}`" for field in legacy_fields)
                + f" FROM `tab{DEVICE_TYPE}`", as_dict=True):
            paired = device.get("pairing_status") == "Paired"
            collect(device.name, "qc", device.get("token_hash"),
                    "Approved" if paired else "Pending",
                    last_seen_at=device.get("last_seen_at"))
            collect(device.name, "qc", device.get("pending_token_hash"), "Pending",
                    last_seen_at=device.get("last_seen_at"))

    for values in credentials.values():
        device_name, service, legacy_hash, status, browser_name, operating_system, last_seen_at = values
        import_legacy_client(device_name, service, legacy_hash, status,
                             browser_name, operating_system, last_seen_at)
        migrated_hash = frappe.db.exists(CLIENT_TYPE, {
            "device": device_name,
            "service_key": service,
            "token_hash": credential_hash(service, legacy_hash=legacy_hash),
        })
        if not migrated_hash:
            frappe.throw(message("error.legacy_device_token_unmigrated").format(count=1),
                         frappe.ValidationError)


def _update_api_docs():
    from factory_management.uqqc.i18n import text

    old = text("docs.device_legacy", "en")
    new = text("docs.device", "en")
    for row in frappe.get_all("API Documentation Endpoint",
                              filters={"description": old}, fields=["name"], limit_page_length=0):
        frappe.db.set_value("API Documentation Endpoint", row.name, "description", new,
                            update_modified=False)


def _retire_master_pairing_fields():
    columns = set(frappe.db.get_table_columns(DEVICE_TYPE))
    token_fields = [field for field in ("token_hash", "pending_token_hash")
                    if field in columns]
    if not token_fields:
        return
    assignments = ", ".join(f"`{field}` = NULL" for field in token_fields)
    frappe.db.sql(f"UPDATE `tab{DEVICE_TYPE}` SET {assignments}")
    for fieldname in ("pairing_status", "token_hash", "pending_token_hash"):
        field_name = frappe.db.get_value("DocField", {"parent": DEVICE_TYPE,
                                                       "fieldname": fieldname}, "name")
        if field_name:
            frappe.db.set_value("DocField", field_name,
                                {"hidden": 1, "in_list_view": 0, "read_only": 1},
                                update_modified=False)


def execute():
    _preflight()
    ensure_module()
    renamed = frappe.db.exists("DocType", "QC Device")
    if renamed:
        frappe.rename_doc("DocType", "QC Device", DEVICE_TYPE, force=True)
        frappe.db.set_value("DocType", DEVICE_TYPE, "module", "Factory Management")
    ensure_device_schema()
    if renamed:
        for row in frappe.get_all(DEVICE_TYPE, fields=["name", "device_uid"], limit_page_length=0):
            uid = row.device_uid.strip()
            if uid != row.device_uid:
                frappe.db.set_value(DEVICE_TYPE, row.name, "device_uid", uid, update_modified=False)
        frappe.db.add_unique(DEVICE_TYPE, ["device_uid"], "factory_device_uid")
    _replace_link_options()
    _migrate_credentials()
    _retire_master_pairing_fields()
    _update_api_docs()
    frappe.clear_cache()
