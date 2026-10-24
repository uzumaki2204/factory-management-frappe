"""Install role policies without replacing API contracts edited in Desk."""

import json

import frappe
from frappe import _

from factory_management.api_access import READER_ROLE, REPORT_ROUTES
from factory_management.install import ensure_schema


OLD_GUARD = '''user = frappe.session.user
if user == "Guest" or (user != "Administrator" and not frappe.db.exists("Has Role", {"parent": user, "role": "System Manager"})):
    frappe.throw(_("QC_REPORT_FORBIDDEN"), frappe.PermissionError)'''
NEW_GUARD = 'frappe.call("factory_management.api_access.authorize_inspection_summary")'


def _upgrade_server_script():
    if not frappe.db.exists("Server Script", "QC Inspection Summary"):
        return
    script = frappe.db.get_value("Server Script", "QC Inspection Summary", "script") or ""
    if NEW_GUARD in script:
        return
    if script.count(OLD_GUARD) != 1:
        frappe.throw(_("QC_REPORT_SCRIPT_MIGRATION_REQUIRED"), frappe.ValidationError)
    frappe.db.set_value("Server Script", "QC Inspection Summary", "script", script.replace(OLD_GUARD, NEW_GUARD, 1))


def _seed_existing_policies():
    for operation_id in REPORT_ROUTES:
        name = frappe.db.get_value("API Documentation Endpoint", {"operation_id": operation_id}, "name")
        if not name:
            continue
        endpoint = frappe.get_doc("API Documentation Endpoint", name)
        changed = False
        if not endpoint.get("allowed_roles"):
            endpoint.append("allowed_roles", {"role": READER_ROLE})
            changed = True
        if operation_id == "qcInspectionSummary":
            responses = json.loads(endpoint.responses_json or "{}")
            if responses.get("403", {}).get("description") == "System Manager role required":
                responses["403"]["description"] = "Role allowed for this QC report API required"
                endpoint.responses_json = json.dumps(responses, ensure_ascii=False)
                changed = True
        if changed:
            endpoint.save(ignore_permissions=True)


def execute():
    ensure_schema()
    _upgrade_server_script()
    _seed_existing_policies()
    frappe.clear_cache()
