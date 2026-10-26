"""Generation fence for QC and UQQC browser data after a source refresh."""

import uuid
from datetime import datetime, timezone

import frappe

from factory_management.device_registry import message


DOCTYPE = "Factory Data Epoch"
NAME = "QC-UQQC"
HEADER = "X-Factory-Data-Epoch"


def current(for_update=False):
    row = frappe.db.get_value(DOCTYPE, NAME, ["generation", "reset_at_utc"],
                              as_dict=True, for_update=for_update)
    return {
        "generation": row.generation if row else "",
        "resetAtUtc": str(row.reset_at_utc) if row else "",
    }


def lock():
    # This row exists even before the first reset. Hold it until transaction end
    # so a tablet write cannot cross the reset transaction with an old epoch.
    frappe.db.get_value("DocType", DOCTYPE, "name", for_update=True)


def require_current():
    lock()
    generation = current(for_update=True)["generation"]
    if generation and (frappe.request.headers.get(HEADER) or "").strip() != generation:
        frappe.throw(message("error.data_epoch"), frappe.PermissionError)


def rotate():
    """Called only by the local, authenticated maintenance workflow."""
    generation = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
    if frappe.db.exists(DOCTYPE, NAME):
        frappe.db.set_value(DOCTYPE, NAME, {"generation": generation, "reset_at_utc": now})
    else:
        frappe.get_doc({"doctype": DOCTYPE, "name": NAME, "generation": generation,
                        "reset_at_utc": now}).insert(ignore_permissions=True, set_name=NAME)
    return generation
