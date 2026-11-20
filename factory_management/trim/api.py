"""System Manager-only Trim import API."""

import frappe

from factory_management.trim.parser import WorkbookError
from factory_management.trim.service import preview_page, queue_import, queue_preview


def _manager():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw("System Manager role is required.", frappe.PermissionError)


def _run(name):
    run = frappe.get_doc("Trim Import Run", name)
    if run.requested_by != frappe.session.user and frappe.session.user != "Administrator":
        frappe.throw("This import belongs to another user.", frappe.PermissionError)
    return run


def _invalid(exc):
    frappe.throw(str(exc), frappe.ValidationError)


@frappe.whitelist(methods=["POST"])
def start_preview(file_url):
    _manager()
    return {"run_name": queue_preview(file_url)}


@frappe.whitelist()
def get_run(run_name):
    _manager()
    run = _run(run_name)
    return {key: run.get(key) for key in (
        "name", "status", "started_at", "completed_at", "source_file",
        "snapshot_token", "snapshot_expires_at", "total_rows", "total_orders",
        "imported_orders", "imported_items", "failed_orders", "message", "error_detail",
    )}


@frappe.whitelist()
def get_preview_page(run_name, token, page=1):
    _manager()
    try:
        return preview_page(_run(run_name), token, page)
    except (WorkbookError, ValueError) as exc:
        _invalid(exc)


@frappe.whitelist(methods=["POST"])
def start_import(run_name, token):
    _manager()
    try:
        return {"run_name": queue_import(_run(run_name), token)}
    except WorkbookError as exc:
        _invalid(exc)
