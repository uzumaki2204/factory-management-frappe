"""Idempotent SPL metadata provisioning."""

from factory_management.spl_po.schema import TYPES


def ensure():
    from factory_management.install import _ensure_snapshot_doctype_shells, ensure_doctype, ensure_module
    ensure_module()
    _ensure_snapshot_doctype_shells()
    for name in ("SPL Purchase Order Item", "SPL Purchase Order", "SPL Import Settings", "SPL Import Run"):
        ensure_doctype(name, TYPES[name], module="Factory Management", is_child=name.endswith("Item"))
