"""Role policies for authenticated QC report methods."""

import frappe
from frappe import _


ENDPOINT_TYPE = "API Documentation Endpoint"
ENDPOINT_ROLE_TYPE = "API Documentation Endpoint Role"
READER_ROLE = "QC Report Reader"
REPORT_ROUTES = {
    "qcInspectionSummary": "/api/method/qc-inspection-summary",
    "qcInspectionSummaryNative": "/api/method/factory_management.qc_reports.inspection_summary",
    "qcReportSummary": "/api/method/factory_management.api.report_summary",
    "qcReportDetail": "/api/method/factory_management.api.report_detail",
    "qcBrotherInspectionSummary": "/api/method/factory_management.qcbrother_reports.inspection_summary",
    "qcBrotherInspectionAggregate": "/api/method/factory_management.qcbrother_reports.inspection_aggregate",
}


def _deny():
    frappe.throw(_("QC_REPORT_FORBIDDEN"), frappe.PermissionError)


def require_report_access(operation_id):
    """Check explicit User roles against the live Desk policy for one report."""
    user = frappe.session.user
    route = REPORT_ROUTES.get(operation_id)
    if not route or not user or user == "Guest":
        _deny()

    endpoint = frappe.db.get_value(
        ENDPOINT_TYPE,
        {"operation_id": operation_id, "path": route, "http_method": "GET", "is_active": 1},
        ["name", "service"],
        as_dict=True,
    )
    if not endpoint:
        _deny()
    service_active = frappe.db.get_value("API Documentation Service", endpoint.service, "is_active")
    if frappe.utils.cint(service_active) != 1:
        _deny()

    allowed = set(frappe.get_all(
        ENDPOINT_ROLE_TYPE,
        filters={"parent": endpoint.name, "parenttype": ENDPOINT_TYPE, "parentfield": "allowed_roles"},
        pluck="role",
    ))
    if not allowed:
        _deny()

    assigned = set(frappe.get_all(
        "Has Role",
        filters={"parent": user, "parenttype": "User", "parentfield": "roles"},
        pluck="role",
    ))
    if not allowed.intersection(assigned):
        _deny()


@frappe.whitelist(methods=["GET"])
def authorize_inspection_summary(**_kwargs):
    """Bridge the Desk Server Script to the same policy as Python reports."""
    require_report_access("qcInspectionSummary")
