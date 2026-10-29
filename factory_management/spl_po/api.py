"""System Manager-only Desk API for SPL preview and import."""

import json

import frappe

from factory_management.spl_po.messages import message
from factory_management.spl_po.parser import WorkbookError
from factory_management.spl_po.service import preview_page, queue_import, queue_preview


def _manager():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(message("SPL_FORBIDDEN"), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def start_preview(file_url=None):
    _manager()
    return {"run_name": queue_preview(file_url=file_url)}


@frappe.whitelist(methods=["POST"])
def test_connection():
    _manager()
    return {"run_name": queue_preview(connection_only=True)}


@frappe.whitelist()
def get_run(run_name):
    _manager()
    run = frappe.get_doc("SPL Import Run", run_name)
    data = {key: run.get(key) for key in (
        "name", "status", "trigger_source", "started_at", "completed_at",
        "snapshot_token", "snapshot_expires_at", "total_rows", "total_orders",
        "imported_orders", "imported_items", "failed_orders", "missing_masters",
        "message", "error_detail",
    )}
    data["run_name"] = run.name
    return data


@frappe.whitelist()
def get_preview_page(run_name, token, page=1, page_size=100):
    _manager()
    try:
        return preview_page(run_name, token, page, page_size)
    except WorkbookError as exc:
        frappe.throw(message(exc.code, **exc.context), frappe.ValidationError)


@frappe.whitelist(methods=["POST"])
def start_import(run_name, token, selected_rows="all", excluded_rows=None):
    _manager()
    if isinstance(selected_rows, str) and selected_rows != "all":
        try:
            selected_rows = json.loads(selected_rows)
        except ValueError:
            frappe.throw(message("SPL_SELECTION_INVALID"), frappe.ValidationError)
    if isinstance(excluded_rows, str):
        try:
            excluded_rows = json.loads(excluded_rows)
        except ValueError:
            frappe.throw(message("SPL_SELECTION_INVALID"), frappe.ValidationError)
    if (selected_rows != "all" and not isinstance(selected_rows, list)) or (
        isinstance(selected_rows, list) and len(selected_rows) > 50_000
    ) or not isinstance(excluded_rows or [], list):
        frappe.throw(message("SPL_SELECTION_INVALID"), frappe.ValidationError)
    try:
        return {"run_name": queue_import(run_name, token, selected_rows, excluded_rows)}
    except WorkbookError as exc:
        frappe.throw(message(exc.code, **exc.context), frappe.ValidationError)
