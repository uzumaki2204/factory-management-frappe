"""Seed editable OpenAPI contracts without replacing Desk customizations."""

import json

import frappe

from factory_management.api_access import READER_ROLE, REPORT_ROUTES
from .service import DIMENSIONS, DETAILS


OPERATIONS = (
    ("qcBrotherInspectionSummary", "summary", 7),
    ("qcBrotherInspectionAggregate", "aggregate", 31),
)


def seed_contracts(service_name):
    for operation, kind, max_days in OPERATIONS:
        if frappe.db.exists("API Documentation Endpoint", {"operation_id": operation}):
            continue
        contract = report_contract(kind, max_days)
        frappe.get_doc({
            "doctype": "API Documentation Endpoint", "service": service_name,
            "operation_id": operation, "path": REPORT_ROUTES[operation], "http_method": "GET",
            "summary": f"QCBROTHER_{kind.upper()}_TITLE",
            "description": f"QCBROTHER_{kind.upper()}_DESCRIPTION",
            "tags_json": _json(["QCBROTHER_REPORTS_TAG"]),
            "parameters_json": _json(contract["parameters"]),
            "responses_json": _json(contract["responses"]),
            "security_json": _json([{"FrappeSession": []}, {"ApiToken": []}]),
            "allowed_roles": [{"role": READER_ROLE}], "is_active": 1,
        }).insert(ignore_permissions=True)


def report_contract(kind, max_days):
    parameters = [{
        "name": name, "in": "query", "required": True,
        "schema": {"type": "string", "format": "date"},
        "description": f"QCBROTHER_DATE_RANGE_{max_days}",
    } for name in ("occurredOnFrom", "occurredOnTo")]
    for name in ("companyId", "companyCode", "qc", "sampleCode"):
        schema = {"type": "string"}
        if name == "companyId":
            schema["format"] = "uuid"
        parameters.append({"name": name, "in": "query", "schema": schema,
                           "description": "QCBROTHER_FILTER_" + name.upper()})
    columns = ("occurredOn", "deviceQc") + DIMENSIONS
    numbers = ("plannedQuantity", "pass", "rework", "defect", "totalPass", "totalRework", "totalDefect")
    if kind == "summary":
        columns += ("eventNo", "deviceNo", "poNumbers") + DETAILS
        numbers = ("quantity",)
        parameters.append({"name": "eventNo", "in": "query", "schema": {"type": "string"},
                           "description": "QCBROTHER_FILTER_EVENTNO"})
    else:
        columns += ("serialNo",)
    properties = {name: {"type": "string"} for name in columns}
    properties["occurredOn"]["format"] = "date-time"
    properties["occurredOn"]["description"] = "QCBROTHER_" + kind.upper() + "_DATE"
    properties.update({name: {"type": "integer", "format": "int32"} for name in numbers})
    schema = {"type": "object", "required": ["message"], "properties": {"message": {
        "type": "array", "items": {"type": "object", "required": list(properties), "properties": properties},
    }}}
    responses = {"200": {"description": "QCBROTHER_REPORT_ROWS", "content": {"application/json": {
        "schema": schema, "example": {"message": []},
    }}}}
    for code, key in (("400", "QCBROTHER_REQUEST_INVALID"), ("401", "QCBROTHER_AUTH_REQUIRED"),
                      ("403", "QC_REPORT_FORBIDDEN"), ("503", "QCBROTHER_SQL_UNAVAILABLE")):
        responses[code] = {"description": key}
    return {"parameters": parameters, "responses": responses}


def _json(value):
    return json.dumps(value, ensure_ascii=False)
