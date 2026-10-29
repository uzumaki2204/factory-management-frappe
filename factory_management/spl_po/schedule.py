"""Configurable SPL import slots evaluated by Frappe's minute scheduler."""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import frappe

from factory_management.spl_po.service import _new_run


def tick():
    if not frappe.db.exists("DocType", "SPL Import Settings"):
        return
    settings = frappe.get_single("SPL Import Settings")
    if not settings.auto_enabled or not settings.customer:
        return
    try:
        local = datetime.now(ZoneInfo(settings.schedule_timezone or "Asia/Ho_Chi_Minh"))
    except ZoneInfoNotFoundError:
        return
    times = {value.strip() for value in (settings.schedule_times or "").split(",") if value.strip()}
    if local.strftime("%H:%M") not in times:
        return
    slot = local.strftime("%Y-%m-%dT%H:%M%z")
    if frappe.db.exists("SPL Import Run", {"schedule_slot": slot}):
        return
    try:
        run = _new_run("Scheduled")
        run.schedule_slot = slot
        run.save(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        frappe.db.rollback()
        return
    frappe.enqueue("factory_management.spl_po.service.execute_import", queue="long", timeout=3600,
                   enqueue_after_commit=True, job_name=f"spl-po-scheduled-{slot}",
                   run_name=run.name, scheduled=True)
