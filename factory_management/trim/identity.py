"""Keep Trim's import identity and quantity correct after Desk edits."""

import hashlib
import json

import frappe


def source_key(order_no, revision_no):
    values = [str(order_no or "").strip(), str(revision_no or "").strip()]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def set_derived_fields(doc, method=None):
    doc.order_no = str(doc.order_no or "").strip()
    doc.revision_no = str(doc.revision_no or "").strip()
    if not doc.order_no:
        frappe.throw(frappe._("Order No is required."))

    key = source_key(doc.order_no, doc.revision_no)
    existing = frappe.db.get_value("Trim", {"source_key": key}, "name")
    if existing and existing != doc.name:
        frappe.throw(frappe._("Trim order {0} / {1} already exists.").format(doc.order_no, doc.revision_no))

    doc.source_key = key
    doc.total_quantity = sum(int(item.order_qty or 0) for item in doc.get("items") or [])
