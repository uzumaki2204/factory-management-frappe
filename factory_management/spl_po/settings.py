"""Validate operator-managed SPL connection and schedule settings."""

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import frappe

from factory_management.spl_po.gateway import GatewayError, _origin
from factory_management.spl_po.messages import message


def validate(doc, _method=None):
    try:
        _origin(doc)
    except GatewayError as exc:
        frappe.throw(message(str(exc)), frappe.ValidationError)
    if doc.client_certificate:
        file_doc = frappe.get_doc("File", doc.client_certificate)
        if not file_doc.is_private:
            frappe.throw(message("SPL_CERT_PRIVATE_REQUIRED"), frappe.ValidationError)
    times = [value.strip() for value in (doc.schedule_times or "").split(",") if value.strip()]
    if (doc.auto_enabled and not times) or any(
        not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value) for value in times
    ):
        frappe.throw(message("SPL_SCHEDULE_INVALID"), frappe.ValidationError)
    try:
        ZoneInfo(doc.schedule_timezone or "Asia/Ho_Chi_Minh")
    except ZoneInfoNotFoundError:
        frappe.throw(message("SPL_TIMEZONE_INVALID"), frappe.ValidationError)
    if not 10 <= int(doc.request_timeout_seconds or 120) <= 600:
        frappe.throw(message("SPL_TIMEOUT_INVALID"), frappe.ValidationError)
    if int(doc.report_offset or 0) < 0:
        frappe.throw(message("SPL_OFFSET_INVALID"), frappe.ValidationError)
