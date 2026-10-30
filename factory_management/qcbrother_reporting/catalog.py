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
        description = "QCBROTHER_FILTER_" + name.upper()
        if kind == "summary" and name in ("companyCode", "qc"):
            description = "QCBROTHER_SUMMARY_FILTER_" + name.upper()
        parameters.append({"name": name, "in": "query", "schema": schema,
                           "description": description})
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
    schema = {
        "type": "array", "items": {"type": "object", "required": list(properties), "properties": properties},
    }
    responses = {"200": {"description": "QCBROTHER_REPORT_ROWS", "content": {"application/json": {
        "schema": schema, "example": summary_example() if kind == "summary" else [],
    }}}}
    for code, key in (("400", "QCBROTHER_REQUEST_INVALID"), ("401", "QCBROTHER_AUTH_REQUIRED"),
                      ("403", "QC_REPORT_FORBIDDEN"),
                      ("503", "QCBROTHER_UQQC_UNAVAILABLE" if kind == "summary" else "QCBROTHER_SQL_UNAVAILABLE")):
        responses[code] = {"description": key}
    return {"parameters": parameters, "responses": responses}


def summary_example():
    defect = {
        "occurredOn": "2026-10-30T00:00:00+07:00", "eventNo": "",
        "deviceNo": "009QC2KT2", "deviceQc": "QC2",
        "companyCode": "KT2", "companyName": "Kim Thành 2", "factoryCode": "",
        "sampleCode": "217H005B", "countryCode": "25", "countryName": "",
        "colorCode": "10", "sizeCode": "XS", "sizeName": "XS",
        "lineCode": "", "lineName": "", "defectCode": "B42", "defectName": "",
        "positionCode": "PLC0022", "positionName": "", "poNumbers": "PO-001", "quantity": 1,
    }
    passed = dict(defect, eventNo="PASS", defectCode="", defectName="",
                  positionCode="", positionName="")
    return [defect, passed]


def refresh_summary_contract():
    """Refresh stock summary examples and descriptions without replacing Desk edits."""
    doctype = "API Documentation Endpoint"
    name = frappe.db.get_value(doctype, {"operation_id": "qcBrotherInspectionSummary"}, "name")
    if not name:
        return
    record = frappe.db.get_value(doctype, name, ["parameters_json", "responses_json"], as_dict=True)
    parameters = json.loads(record.parameters_json or "[]")
    responses = json.loads(record.responses_json or "{}")
    changed = False
    for parameter in parameters:
        if parameter.get("name") in ("companyCode", "qc"):
            old = "QCBROTHER_FILTER_" + parameter["name"].upper()
            if parameter.get("description") == old:
                parameter["description"] = "QCBROTHER_SUMMARY_FILTER_" + parameter["name"].upper()
                changed = True
    success = responses.get("200", {}).get("content", {}).get("application/json", {})
    if success.get("example") == []:
        success["example"] = summary_example()
        changed = True
    unavailable = responses.get("503", {})
    if unavailable.get("description") == "QCBROTHER_SQL_UNAVAILABLE":
        unavailable["description"] = "QCBROTHER_UQQC_UNAVAILABLE"
        changed = True
    if changed:
        frappe.db.set_value(doctype, name, {
            "parameters_json": _json(parameters), "responses_json": _json(responses),
        }, update_modified=False)


def _json(value):
    return json.dumps(value, ensure_ascii=False)
