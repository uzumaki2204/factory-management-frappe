"""Generate stable Factory names from the factory code and owning company."""

import frappe
from frappe.model.naming import validate_name

from factory_management.device_registry import message


MAX_NAME_LENGTH = 140


def before_naming(doc, method=None):
    code = (doc.get("factory_code") or "").strip()
    company = (doc.get("company") or "").strip()
    identity = doc.name or code or "Factory"

    if (
        not code
        or not company
        or code != doc.get("factory_code")
        or company != doc.get("company")
        or not frappe.db.exists("Company", company)
    ):
        frappe.throw(
            message("error.factory_identity_invalid").format(factory=identity),
            frappe.ValidationError,
        )

    name = f"{code}-{company}"
    if len(name) > MAX_NAME_LENGTH:
        frappe.throw(
            message("error.factory_identity_invalid").format(factory=identity),
            frappe.ValidationError,
        )

    try:
        doc.factory_key = validate_name("Factory", name)
    except frappe.NameError:
        frappe.throw(
            message("error.factory_identity_invalid").format(factory=identity),
            frappe.ValidationError,
        )
