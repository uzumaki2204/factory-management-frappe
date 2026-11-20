"""Create Trim DocTypes during installation and migration."""

from factory_management.trim.schema import TYPES


def ensure():
    from factory_management.install import ensure_doctype, ensure_module
    ensure_module()
    for name in ("Trim Item", "Trim", "Trim Import Run"):
        ensure_doctype(name, TYPES[name], module="Factory Management", is_child=name == "Trim Item")
    # The first release could create Snapshot Path as Data; widen it in place.
    import frappe
    run_type = frappe.get_doc("DocType", "Trim Import Run")
    snapshot_field = next(row for row in run_type.fields if row.fieldname == "snapshot_path")
    if snapshot_field.fieldtype != "Small Text":
        snapshot_field.fieldtype = "Small Text"
        run_type.save(ignore_permissions=True)
