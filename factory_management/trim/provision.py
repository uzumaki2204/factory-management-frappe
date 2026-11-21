"""Create Trim DocTypes during installation and migration."""

import frappe

from factory_management.trim.schema import TYPES


ROLE = "Trim Manager"


def ensure_role():
    if not frappe.db.exists("Role", ROLE):
        frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(ignore_permissions=True)


def ensure():
    from factory_management.install import ensure_doctype, ensure_module

    ensure_role()
    ensure_module()
    for name in ("Trim Item", "Trim", "Trim Import Run"):
        ensure_doctype(name, TYPES[name], module="Factory Management", is_child=name == "Trim Item")
    # The first release could create Snapshot Path as Data; widen it in place.
    run_type = frappe.get_doc("DocType", "Trim Import Run")
    snapshot_field = next(row for row in run_type.fields if row.fieldname == "snapshot_path")
    if snapshot_field.fieldtype != "Small Text":
        snapshot_field.fieldtype = "Small Text"
        run_type.save(ignore_permissions=True)
    for name, permissions in (
        ("Trim", {"read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1}),
        ("Trim Import Run", {"read": 1, "report": 1, "export": 1}),
    ):
        doctype = frappe.get_doc("DocType", name)
        if not any(row.role == ROLE and row.permlevel == 0 for row in doctype.permissions):
            doctype.append("permissions", {"role": ROLE, "permlevel": 0, **permissions})
            doctype.save(ignore_permissions=True)
