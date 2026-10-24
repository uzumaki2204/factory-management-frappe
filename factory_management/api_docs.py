"""Editable API contracts in Desk, rendered as OpenAPI for Swagger UI."""

import json
import re
from urllib.parse import urlparse

import frappe
from frappe import _
from factory_management.api_access import ENDPOINT_ROLE_TYPE, READER_ROLE, REPORT_ROUTES


SERVICE_TYPE = "API Documentation Service"
ENDPOINT_TYPE = "API Documentation Endpoint"


def _manager_only():
    frappe.only_for("System Manager")


def _translate_descriptions(value):
    if isinstance(value, list):
        return [_translate_descriptions(item) for item in value]
    if isinstance(value, dict):
        return {key: _(item) if key in {"description", "summary"} and isinstance(item, str) else _translate_descriptions(item) for key, item in value.items()}
    return value


def _json_field(row, field, expected, default):
    value = row.get(field)
    if not value:
        return default
    try:
        result = json.loads(value)
    except (TypeError, ValueError):
        frappe.throw(_("Invalid API documentation JSON in {0}").format(row.operation_id), frappe.ValidationError)
    if not isinstance(result, expected):
        frappe.throw(_("Invalid API documentation JSON in {0}").format(row.operation_id), frappe.ValidationError)
    return result


@frappe.whitelist(methods=["GET"])
def services():
    _manager_only()
    rows = frappe.get_all(
        SERVICE_TYPE,
        filters={"is_active": 1},
        fields=["service_key", "service_title", "version", "description", "base_url", "openapi_url"],
        order_by="service_title asc",
    )
    return [
        {
            "key": row.service_key,
            "title": _(row.service_title),
            "version": row.version,
            "description": _(row.description) if row.description else "",
            "openapiUrl": row.openapi_url,
        }
        for row in rows
    ]


@frappe.whitelist(methods=["GET"])
def openapi(service="qc"):
    _manager_only()
    service_name = frappe.db.get_value(SERVICE_TYPE, {"service_key": service, "is_active": 1}, "name")
    if not service_name:
        frappe.throw(_("API documentation service was not found"), frappe.DoesNotExistError)
    doc = frappe.get_doc(SERVICE_TYPE, service_name)
    rows = frappe.get_all(
        ENDPOINT_TYPE,
        filters={"service": service_name, "is_active": 1},
        fields=["name", "operation_id", "path", "http_method", "summary", "description", "tags_json", "parameters_json", "request_body_json", "responses_json", "security_json"],
        order_by="path asc, http_method asc",
    )
    roles_by_endpoint = {row.name: [] for row in rows}
    if roles_by_endpoint:
        role_rows = frappe.get_all(
            ENDPOINT_ROLE_TYPE,
            filters={"parent": ["in", list(roles_by_endpoint)], "parenttype": ENDPOINT_TYPE, "parentfield": "allowed_roles"},
            fields=["parent", "role"],
        )
        for role_row in role_rows:
            roles_by_endpoint[role_row.parent].append(role_row.role)
    paths = {}
    for row in rows:
        method = (row.http_method or "").lower()
        if not row.path.startswith("/") or method not in {"get", "post", "put", "patch", "delete"}:
            frappe.throw(_("Invalid API documentation route in {0}").format(row.operation_id), frappe.ValidationError)
        if method in paths.get(row.path, {}):
            frappe.throw(_("Duplicate API documentation route in {0}").format(row.operation_id), frappe.ValidationError)
        operation = {
            "operationId": row.operation_id,
            "summary": _(row.summary),
            "description": _(row.description) if row.description else "",
            "tags": [_(tag) for tag in _json_field(row, "tags_json", list, [])],
            "parameters": _translate_descriptions(_json_field(row, "parameters_json", list, [])),
            "responses": _translate_descriptions(_json_field(row, "responses_json", dict, {})),
            "security": _json_field(row, "security_json", list, [{"FrappeSession": []}, {"ApiToken": []}]),
        }
        if row.operation_id in REPORT_ROUTES or row.operation_id.startswith("uqqc_"):
            operation["x-allowed-roles"] = sorted(roles_by_endpoint[row.name])
        body = _json_field(row, "request_body_json", dict, {})
        if body:
            operation["requestBody"] = body
        paths.setdefault(row.path, {})[method] = operation
    return {
        "openapi": "3.1.0",
        "info": {
            "title": _(doc.service_title),
            "version": doc.version or "1.0.0",
            "description": _(doc.description) if doc.description else "",
        },
        "servers": [{"url": (doc.base_url or frappe.utils.get_url()).rstrip("/")}],
        "components": {
            "securitySchemes": {
                "FrappeSession": {"type": "apiKey", "in": "cookie", "name": "sid", "description": _("Frappe Desk session")},
                "ApiToken": {"type": "apiKey", "in": "header", "name": "Authorization", "description": _("token api_key:api_secret")},
                **({"UQQCDeviceToken": {"type": "apiKey", "in": "header", "name": "X-UQQC-Token"}} if doc.service_key == "uqqc" else {}),
            }
        },
        "paths": paths,
    }


def _seed_summary_contract(service_name):
    if frappe.db.exists(ENDPOINT_TYPE, {"operation_id": "qcInspectionSummary"}):
        return
    names = [
        "event_type", "entity_type", "device_name", "device_no", "device_qc", "device_company",
        "companies_code", "companies_name", "factories_code", "factories_name",
        "production_lines_code", "production_lines_name", "customers_code", "customers_name",
        "products_code", "products_name", "colors_code", "colors_name", "sizes_code", "sizes_name",
        "qc_defect_groups_code", "qc_defect_groups_name", "qc_defects_code", "qc_defects_name",
    ]
    parameters = [
        {"name": name, "in": "query", "required": True, "schema": {"type": "string", "format": "date"}, "description": "UTC date of occurred_at"}
        for name in ("date_from", "date_to")
    ]
    parameters += [{"name": name, "in": "query", "schema": {"type": "string"}} for name in names]
    parameters.append({"name": "quantity_summary", "in": "query", "schema": {"type": "integer"}})
    properties = {}
    columns = [
        "eventType", "entityType", "deviceName", "deviceNo", "deviceQc", "deviceCompany",
        "companiesCode", "companiesName", "factoriesCode", "factoriesName",
        "productionLinesCode", "productionLinesName", "lineGroupsCode", "lineGroupsName",
        "customersCode", "customersName", "productsCode", "productsName",
        "colorsCode", "colorsName", "sizesCode", "sizesName",
        "qcDefectGroupsCode", "qcDefectGroupsName", "qcDefectsCode", "qcDefectsName",
    ]
    for name in columns:
        properties[name] = {"type": ["string", "null"]}
    properties["occurredDate"] = {"type": "string", "format": "date"}
    properties["quantitySummary"] = {"type": "integer"}
    responses = {
        "200": {
            "description": "Grouped inspection events",
            "content": {"application/json": {"schema": {
                "type": "object", "required": ["message"],
                "properties": {"message": {"type": "array", "items": {"type": "object", "properties": properties}}},
            }}},
        },
        "400": {"description": "Missing or invalid date range or quantity"},
        "403": {"description": "Role allowed for this QC report API required"},
    }
    frappe.get_doc({
        "doctype": ENDPOINT_TYPE,
        "service": service_name,
        "operation_id": "qcInspectionSummary",
        "path": "/api/method/qc-inspection-summary",
        "http_method": "GET",
        "summary": "QC inspection summary",
        "description": "Groups QC Inspection Event quantity_delta by date, device, company, factory, line, line group, customer, product, color, size and defect. Maximum date range: 7 days.",
        "tags_json": json.dumps(["QC Reports"]),
        "parameters_json": json.dumps(parameters),
        "responses_json": json.dumps(responses),
        "security_json": json.dumps([{"FrappeSession": []}, {"ApiToken": []}]),
        "allowed_roles": [{"role": READER_ROLE}],
        "is_active": 1,
    }).insert(ignore_permissions=True)


def _seed_python_report_contract(service_name, operation_id, method_name, title, description, columns):
    if frappe.db.exists(ENDPOINT_TYPE, {"operation_id": operation_id}):
        return
    parameters = [
        {"name": name, "in": "query", "required": True, "schema": {"type": "string", "format": "date"}}
        for name in ("date_from", "date_to")
    ]
    parameters += [
        {"name": name, "in": "query", "schema": {"type": "string"}}
        for name in ("event_type", "device", "product", "line", "color", "size", "defect")
    ]
    properties = {name: {"type": ["string", "null"]} for name in columns}
    if "quantity" in properties:
        properties["quantity"] = {"type": "integer"}
    if "quantity_delta" in properties:
        properties["quantity_delta"] = {"type": ["integer", "null"]}
    responses = {
        "200": {"description": "QC report rows", "content": {"application/json": {"schema": {
            "type": "object", "required": ["message"],
            "properties": {"message": {"type": "array", "items": {"type": "object", "properties": properties}}},
        }}}},
        "400": {"description": "Missing or invalid date range or quantity"},
        "403": {"description": "Role allowed for this QC report API required"},
    }
    frappe.get_doc({
        "doctype": ENDPOINT_TYPE,
        "service": service_name,
        "operation_id": operation_id,
        "path": f"/api/method/factory_management.api.{method_name}",
        "http_method": "GET",
        "summary": title,
        "description": description,
        "tags_json": json.dumps(["QC Reports"]),
        "parameters_json": json.dumps(parameters),
        "responses_json": json.dumps(responses),
        "security_json": json.dumps([{"FrappeSession": []}, {"ApiToken": []}]),
        "allowed_roles": [{"role": READER_ROLE}],
        "is_active": 1,
    }).insert(ignore_permissions=True)


def _seed_python_reports(service_name):
    _seed_python_report_contract(
        service_name, "qcReportSummary", "report_summary", "QC report summary",
        "Groups QC Inspection Event quantities by local date, device, product, line, event type and defect. Maximum date range: 7 days.",
        ("date", "device", "product", "line", "event_type", "defect", "quantity"),
    )
    _seed_python_report_contract(
        service_name, "qcReportDetail", "report_detail", "QC report detail",
        "Returns QC Inspection Event rows. Maximum date range: 7 days.",
        ("name", "device", "event_type", "event_key", "entity_type", "product", "line", "color", "size", "defect", "quantity_delta", "occurred_at", "synced_at"),
    )


def ensure_catalog():
    """Add starter records once; later Desk edits are preserved."""
    service_name = frappe.db.get_value(SERVICE_TYPE, {"service_key": "qc"}, "name")
    if not service_name:
        service_name = frappe.get_doc({
            "doctype": SERVICE_TYPE,
            "service_key": "qc",
            "service_title": "QC API",
            "version": "1.0.0",
            "description": "Quality Control APIs. Contracts are editable in Frappe Desk.",
            "is_active": 1,
        }).insert(ignore_permissions=True).name
    _seed_summary_contract(service_name)
    _seed_python_reports(service_name)
    if not frappe.db.exists("Page", "qc-api-docs"):
        frappe.get_doc({
            "doctype": "Page",
            "page_name": "qc-api-docs",
            "title": "API Documentation",
            "module": "API Management",
            "standard": "No",
        }).insert(ignore_permissions=True)
    page = frappe.get_doc("Page", "qc-api-docs")
    changed = False
    if page.module != "API Management":
        page.module = "API Management"
        changed = True
    if not any(row.role == "System Manager" for row in page.roles):
        page.append("roles", {"role": "System Manager"})
        changed = True
    if changed:
        page.save(ignore_permissions=True)


def validate_service(doc, method=None):
    if not re.fullmatch(r"[a-z0-9_-]+", doc.service_key or ""):
        frappe.throw(_("Invalid API documentation service key"), frappe.ValidationError)
    for field in ("base_url", "openapi_url"):
        value = (doc.get(field) or "").strip()
        if not value:
            continue
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            frappe.throw(_("Invalid API documentation URL"), frappe.ValidationError)


def validate_endpoint(doc, method=None):
    if not (doc.path or "").startswith("/") or (doc.http_method or "").lower() not in {"get", "post", "put", "patch", "delete"}:
        frappe.throw(_("Invalid API documentation route in {0}").format(doc.operation_id), frappe.ValidationError)
    for field, expected in (
        ("tags_json", list), ("parameters_json", list), ("request_body_json", dict),
        ("responses_json", dict), ("security_json", list),
    ):
        _json_field(doc, field, expected, [] if expected is list else {})
    roles = [row.role for row in doc.get("allowed_roles") or []]
    if len(roles) != len(set(roles)):
        frappe.throw(_("Duplicate allowed API role in {0}").format(doc.operation_id), frappe.ValidationError)
    other = frappe.db.exists(ENDPOINT_TYPE, {
        "service": doc.service, "path": doc.path, "http_method": doc.http_method,
        "name": ["!=", doc.name],
    })
    if other:
        frappe.throw(_("Duplicate API documentation route in {0}").format(doc.operation_id), frappe.ValidationError)
