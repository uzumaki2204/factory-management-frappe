"""Explicit, one-time event reset after an operator has backed up the site.

Run with bench execute on the selected site. This command is intentionally not in
patches.txt because publishing app code must not delete another site's history.
"""

import json

import frappe

from factory_management.api_docs import retire_inspection_event_contract_fields
from factory_management.data_epoch import rotate
from factory_management.device_registry import message
from factory_management.install import ensure_schema
from factory_management import __version__


RETIRED_FIELDS = {
    "QC Inspection Event": ("event_key", "entity_type", "entity_id", "payload_json"),
    "UQQC Inspection Event": ("event_uid", "fingerprint", "server_date_key"),
}


def status():
    """Read-only state check for the selected Frappe site."""
    from factory_management.data_epoch import current

    report_script = frappe.db.get_value("Server Script", "QC Inspection Summary", "script") or ""
    contract_fields = {}
    for operation in ("qcInspectionSummary", "qcReportDetail"):
        row = frappe.db.get_value("API Documentation Endpoint", {"operation_id": operation},
                                  ["parameters_json", "responses_json"], as_dict=True)
        if not row:
            continue
        parameters = json.loads(row.parameters_json or "[]")
        responses = json.loads(row.responses_json or "{}")
        properties = (responses.get("200", {}).get("content", {}).get("application/json", {})
                      .get("schema", {}).get("properties", {}).get("message", {}).get("items", {})
                      .get("properties", {}))
        contract_fields[operation] = sorted({item.get("name") for item in parameters
                                             if item.get("name") in {"entity_type"}} |
                                            (set(properties) & {"entityType", "entity_type", "event_key"}))
    return {
        "app_version": __version__,
        "event_counts": {doctype: frappe.db.count(doctype) for doctype in RETIRED_FIELDS},
        "retired_doctype_fields": {
            doctype: sorted({field.fieldname for field in frappe.get_meta(doctype).fields}.intersection(fields))
            for doctype, fields in RETIRED_FIELDS.items()
        },
        "retired_columns": {
            doctype: sorted(set(frappe.db.get_table_columns(doctype)).intersection(fields))
            for doctype, fields in RETIRED_FIELDS.items()
        },
        "report_script_uses_retired_column": "e.entity_type" in report_script,
        "api_contract_retired_fields": contract_fields,
        "data_epoch": current(),
    }


def _update_report_script():
    name = "QC Inspection Summary"
    if not frappe.db.exists("Server Script", name):
        return
    script = frappe.db.get_value("Server Script", name, "script") or ""
    updated = script.replace('    "entity_type": ("e.entity_type", "contains"),\n', "")
    updated = updated.replace("    e.entity_type AS entityType,\n", "")
    updated = updated.replace("GROUP BY e.event_type, e.entity_type,", "GROUP BY e.event_type,")
    if "e.entity_type" in updated:
        frappe.throw(message("error.event_retire_script"), frappe.ValidationError)
    if updated != script:
        frappe.db.set_value("Server Script", name, "script", updated, update_modified=False)


def _remove_field_metadata():
    for doctype, fields in RETIRED_FIELDS.items():
        for field in fields:
            for name in frappe.get_all("Property Setter", filters={"doc_type": doctype, "field_name": field}, pluck="name"):
                frappe.delete_doc("Property Setter", name, ignore_permissions=True)
            for name in frappe.get_all("Custom Field", filters={"dt": doctype, "fieldname": field}, pluck="name"):
                frappe.delete_doc("Custom Field", name, ignore_permissions=True)


def execute():
    """Clear the two event tables, rotate the browser epoch, and drop only retired columns."""
    # Old columns provide a durable idempotency marker. A second execution must
    # not delete events recorded after this migration.
    columns = {
        doctype: set(frappe.db.get_table_columns(doctype))
        for doctype in RETIRED_FIELDS
    }
    if not any(columns[doctype].intersection(fields) for doctype, fields in RETIRED_FIELDS.items()):
        return

    _update_report_script()
    _remove_field_metadata()
    ensure_schema()
    retire_inspection_event_contract_fields()

    for doctype in RETIRED_FIELDS:
        frappe.db.delete(doctype)
    rotate()

    for doctype, fields in RETIRED_FIELDS.items():
        for field in fields:
            if field in columns[doctype]:
                frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN `{field}`")
        frappe.clear_cache(doctype=doctype)
