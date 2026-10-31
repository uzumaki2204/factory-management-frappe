"""Return QC/UQQC business data directly at the HTTP boundary."""

import gzip

import frappe


MODULES = (
    "factory_management.api.",
    "factory_management.qc_reports.",
    "factory_management.qcbrother_reports.",
    "factory_management.uqqc.api.",
)


def direct_qc_response(response, request):
    if not 200 <= response.status_code < 300 or not response.is_json:
        return
    method = _request_method(request)
    if not is_qc_method(method):
        return
    payload = response.get_json(silent=True)
    if isinstance(payload, dict) and "message" in payload and not any(
            key in payload for key in ("exc", "exc_type", "exception")):
        response.set_data(frappe.as_json(payload["message"]))
    if method != "uqqc-bootstrap" or response.headers.get("Content-Encoding"):
        return
    accepted = getattr(request, "accept_encodings", None)
    if accepted is None or accepted.quality("gzip") <= 0:
        return
    body = response.get_data()
    if len(body) < 1024:
        return
    response.set_data(gzip.compress(body, compresslevel=6))
    response.headers["Content-Encoding"] = "gzip"
    vary = response.headers.get("Vary", "")
    if "accept-encoding" not in vary.lower():
        response.headers["Vary"] = ", ".join(part for part in (vary, "Accept-Encoding") if part)


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
