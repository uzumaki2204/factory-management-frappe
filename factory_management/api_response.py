"""Return QC/UQQC business data directly at the HTTP boundary."""

import frappe


MODULES = (
    "factory_management.api.",
    "factory_management.qcbrother_reports.",
    "factory_management.uqqc.api.",
)


def direct_qc_response(response, request):
    if not 200 <= response.status_code < 300 or not response.is_json:
        return
    if not is_qc_method(_request_method(request)):
        return
    payload = response.get_json(silent=True)
    if not isinstance(payload, dict) or "message" not in payload:
        return
    if any(key in payload for key in ("exc", "exc_type", "exception")):
        return
    response.set_data(frappe.as_json(payload["message"]))


def is_qc_method(method):
    if method.startswith(MODULES) or method == "qc-inspection-summary":
        return True
    if not method.startswith("uqqc-"):
        return False
    from factory_management.uqqc.access import OPERATIONS

    return method in {alias for _, alias in OPERATIONS.values()}


def _request_method(request):
    for prefix in ("/api/method/", "/api/v1/method/"):
        if request.path.startswith(prefix):
            return request.path[len(prefix):].rstrip("/")
    if request.path.rstrip("/") in ("", "/api/method", "/api/v1/method"):
        return frappe.form_dict.get("cmd", "") or ""
    return ""
