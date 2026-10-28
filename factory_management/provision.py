"""Provision the Desk-editable QC summary Server Script once."""
from pathlib import Path

import frappe


def ensure_qc_inspection_summary():
    if frappe.db.exists("Server Script", "QC Inspection Summary"):
        return "existing"
    source = Path(__file__).parent / "server_scripts" / "qc_inspection_summary.py"
    doc = frappe.get_doc({
        "doctype": "Server Script",
        "name": "QC Inspection Summary",
        "script_type": "API",
        "api_method": "qc-inspection-summary",
        "allow_guest": 0,
        "disabled": 0,
        "script": source.read_text(encoding="utf-8"),
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name
