"""Live endpoint policy and device authentication for UQQC."""

import frappe

from factory_management import device_registry
from factory_management import data_epoch
from factory_management.uqqc.i18n import fail


OPERATIONS = {
    "bootstrap": ("GET", "uqqc-bootstrap"),
    "device_register": ("POST", "uqqc-device-register"),
    "device_check": ("POST", "uqqc-device-check"),
    "sync": ("POST", "uqqc-inspections-sync"),
    "snapshot": ("POST", "uqqc-inspections-snapshot"),
    "detail_snapshot": ("POST", "uqqc-inspections-detail-snapshot"),
}


def endpoint_policy(operation):
    if operation in ("device_register", "device_check", "sync"):
        data_epoch.require_current()
    rule = OPERATIONS.get(operation)
    if not rule:
        fail("api.forbidden", permission=True)
    method, api_method = rule
    if frappe.request.method != method or frappe.request.path.rstrip("/") != "/api/method/" + api_method:
        fail("api.forbidden", permission=True)
    endpoint = frappe.db.get_value(
        "API Documentation Endpoint",
        {"operation_id": "uqqc_" + operation, "path": "/api/method/" + api_method,
         "http_method": method, "is_active": 1},
        ["name", "service"], as_dict=True,
    )
    service = frappe.db.get_value("API Documentation Service", endpoint.service,
                                  ["service_key", "is_active"], as_dict=True) if endpoint else None
    if not service or service.service_key != "uqqc" or service.is_active != 1:
        fail("api.forbidden", permission=True)
    return endpoint


def find_device(device_id):
    if not isinstance(device_id, str) or not frappe.db.exists(device_registry.DEVICE_TYPE, device_id):
        fail("api.device_missing", permission=True)
    return frappe.get_doc(device_registry.DEVICE_TYPE, device_id)


def approved_device(device_id, endpoint=None, for_update=False):
    device = find_device(device_id)
    if for_update:
        # Hold the device row until the request commits, serializing its writers.
        state = frappe.db.get_value(device_registry.DEVICE_TYPE, device.name,
                                    ["name", "status", "is_active", "company"],
                                    as_dict=True, for_update=True)
        if not state:
            fail("api.device_missing", permission=True)
        device.update(state)
    if device.status != "Approved" or not device.is_active or not device.company:
        fail("api.device_pending", permission=True)
    return device
