"""Additive UQQC installation; preserve subsequent Desk edits."""

import json
from pathlib import Path

import frappe

from factory_management.install import ensure_doctype, field
from factory_management.uqqc.access import OPERATIONS
from factory_management.uqqc.i18n import text


ROOT = Path(__file__).parent
CATALOG_MANAGER_ROLE = "UQQC Catalog Manager"
CATALOG_TYPES = (
    "UQQC Defect", "UQQC Defect Position",
)


def _field(name, kind="Data", options=None, **extra):
    return field(name, text("field." + name, "en"), kind, options, **extra)


def _ensure_catalog_permission(doctype):
    document = frappe.get_doc("DocType", doctype)
    if any(row.role == CATALOG_MANAGER_ROLE and not row.permlevel for row in document.permissions):
        return
    document.append("permissions", {
        "role": CATALOG_MANAGER_ROLE, "permlevel": 0,
        "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1,
    })
    document.save(ignore_permissions=True)
    frappe.clear_cache(doctype=doctype)


def ensure_schema():
    owner = frappe.db.get_value("Module Def", "UQQC", "app_name")
    if owner and owner != "factory_management":
        frappe.throw(text("api.namespace_conflict"), frappe.ValidationError)
    for doctype in (*CATALOG_TYPES, "UQQC Inspection Event"):
        module = frappe.db.get_value("DocType", doctype, "module")
        if module and module != "UQQC":
            frappe.throw(text("api.namespace_conflict"), frappe.ValidationError)
    if not frappe.db.exists("Module Def", "UQQC"):
        frappe.get_doc({"doctype": "Module Def", "module_name": "UQQC", "app_name": "factory_management"}).insert(ignore_permissions=True)
    if not frappe.db.exists("Role", CATALOG_MANAGER_ROLE):
        frappe.get_doc({"doctype": "Role", "role_name": CATALOG_MANAGER_ROLE, "desk_access": 1}).insert(ignore_permissions=True)
    catalog = {
        "UQQC Defect": [
            _field("record_type", "Select", "Group\nDefect", reqd=1, default="Defect", in_list_view=1),
            _field("code", reqd=1, in_list_view=1),
            _field("title", reqd=1, in_list_view=1),
            _field("defect_group", "Link", "UQQC Defect"),
            _field("severity"),
            _field("is_active", "Check", default="1"),
            _field("legacy_id", read_only=1),
        ],
        "UQQC Defect Position": [
            _field("record_type", "Select", "Group\nPosition", reqd=1, default="Position", in_list_view=1),
            _field("code", reqd=1, in_list_view=1),
            _field("title", reqd=1, in_list_view=1),
            _field("position_group", "Link", "UQQC Defect Position"),
            _field("is_active", "Check", default="1"),
            _field("legacy_id", read_only=1),
        ],
    }
    for doctype, fields in catalog.items():
        ensure_doctype(doctype, fields, module="UQQC")
        _ensure_catalog_permission(doctype)
    ensure_doctype("UQQC Inspection Event", [
        _field("local_event_id", reqd=1, read_only=1),
        _field("device", "Link", "Factory Device", reqd=1, in_list_view=1),
        _field("event_kind", "Select", "pass\nrework\ndefect", reqd=1, in_list_view=1),
        _field("line", "Link", "Production Line", reqd=1),
        _field("product", "Link", "Product", reqd=1, in_list_view=1),
        _field("color", "Link", "Product Color", reqd=1),
        _field("size", "Link", "ProductSize", reqd=1),
        _field("market", "Link", "Market", reqd=1),
        _field("defect", "Link", "UQQC Defect"),
        _field("defect_position", "Link", "UQQC Defect Position"),
        _field("defect_piece_id"), _field("schema_version", "Int"),
        _field("quantity", "Int", reqd=1, default="1"),
        _field("occurred_at", "Datetime", reqd=1, in_list_view=1),
        _field("synced_at", "Datetime", reqd=1),
    ], module="UQQC")
    frappe.db.add_index("UQQC Inspection Event", ["device", "occurred_at"], "uqqc_device_occurred")


def ensure_catalog():
    service = frappe.db.get_value("API Documentation Service", {"service_key": "uqqc"}, "name")
    if not service:
        service = frappe.get_doc({
            "doctype": "API Documentation Service", "service_key": "uqqc", "service_title": "UQQC API",
            "version": "1.0.0", "description": text("docs.description", "en"), "is_active": 1,
        }).insert(ignore_permissions=True).name
    string = {"type": "string"}
    device_id_schema = {"type": "string", "format": "uuid"}
    scope_properties = {key: string for key in ("lineId", "productId", "colorId", "sizeId", "marketId")}
    event_properties = {
        **scope_properties, "localEventId": {"type": "string", "minLength": 1, "maxLength": 100},
        "occurredAt": {"type": "string", "format": "date-time"}, "schemaVersion": {"type": "integer", "enum": [1, 2]},
        "defectId": string, "defectPositionId": string, "defectPieceId": {"type": "string", "format": "uuid"},
        "quantityDelta": {"type": "integer", "const": 1},
    }
    event_schema = {"type": "object", "properties": event_properties,
                    "required": [*scope_properties, "localEventId", "occurredAt"]}
    for operation, (method, api_method) in OPERATIONS.items():
        existing = frappe.db.get_value("API Documentation Endpoint", {"operation_id": "uqqc_" + operation}, "name")
        properties = {"id": device_id_schema}
        required = ["id"]
        if operation == "snapshot":
            properties.update(scope_properties)
            required += list(scope_properties)
        if operation == "sync":
            properties.update({key: {"type": "array", "maxItems": 500, "items": event_schema}
                               for key in ("events", "passEvents", "reworkEvents")})
        body = {} if method == "GET" else {"required": True, "content": {"application/json": {"schema": {
            "type": "object", "properties": properties, "required": required,
        }}}}
        security = []
        description = text("docs." + operation + "_catalog", "en") if operation in ("bootstrap", "sync") else text("docs.device", "en")
        parameters = [{"name": "id", "in": "query", "required": True, "schema": device_id_schema}] if method == "GET" else []
        if existing:
            current = frappe.db.get_value("API Documentation Endpoint", existing,
                                          ["security_json", "parameters_json", "request_body_json"], as_dict=True)
            old_contract = "UQQCDeviceToken" in (current.security_json or "") or any(
                '"deviceId"' in (value or "") for value in
                (current.parameters_json, current.request_body_json))
            if old_contract:
                frappe.db.set_value("API Documentation Endpoint", existing, {
                    "description": description,
                    "parameters_json": json.dumps(parameters),
                    "request_body_json": json.dumps(body),
                    "security_json": json.dumps(security),
                }, update_modified=False)
                frappe.db.delete("API Documentation Endpoint Role", {"parent": existing})
            continue
        frappe.get_doc({
            "doctype": "API Documentation Endpoint", "service": service, "operation_id": "uqqc_" + operation,
            "path": "/api/method/" + api_method, "http_method": method, "summary": text("docs." + operation, "en"),
            "description": description,
            "tags_json": json.dumps(["UQQC"]),
            "parameters_json": json.dumps(parameters),
            "request_body_json": json.dumps(body), "security_json": json.dumps(security),
            "responses_json": json.dumps({"200": {"description": text("docs.success", "en"), "content": {"application/json": {"schema": {
                "type": "object", "properties": {"message": {"type": "object"}}, "required": ["message"],
            }}}}, "403": {"description": text("api.forbidden", "en")},
                "409": {"description": text("api.retry_sync", "en")}, "417": {"description": text("api.input", "en")}}),
            "allowed_roles": [], "is_active": 1,
        }).insert(ignore_permissions=True)


def ensure_scripts():
    for operation, (_, api_method) in OPERATIONS.items():
        name = "UQQC " + operation.replace("_", " ").title()
        existing = frappe.db.get_value("Server Script", {"api_method": api_method}, "name")
        if existing:
            if frappe.db.get_value("Server Script", existing, "module") != "UQQC":
                frappe.throw(text("api.script_conflict"), frappe.ValidationError)
            continue
        if frappe.db.exists("Server Script", name):
            frappe.throw(text("api.script_conflict"), frappe.ValidationError)
        frappe.get_doc({
            "doctype": "Server Script", "name": name, "script_type": "API", "api_method": api_method,
            "module": "UQQC", "allow_guest": 1, "disabled": 0,
            "script": (ROOT / "server_scripts" / (operation + ".py")).read_text(encoding="utf-8"),
        }).insert(ignore_permissions=True)


def ensure():
    ensure_schema()
    ensure_catalog()
    ensure_scripts()
    from factory_management.uqqc.web_page import ensure_page
    ensure_page()
    frappe.clear_cache()
