"""Migrate only the success envelope in editable QC/UQQC contracts."""

import json

import frappe

from factory_management.api_response import is_qc_method


def migrate_success_contracts():
    for service in frappe.get_all("API Documentation Service", filters={
        "service_key": ["in", ["qc", "uqqc"]],
    }, fields=["name", "version"]):
        endpoints = frappe.get_all("API Documentation Endpoint", filters={"service": service.name},
                                   fields=["name", "path", "responses_json"])
        for endpoint in endpoints:
            method = (endpoint.path or "").removeprefix("/api/method/")
            if not is_qc_method(method):
                continue
            responses = json.loads(endpoint.responses_json or "{}")
            if unwrap_success_contract(responses):
                frappe.db.set_value("API Documentation Endpoint", endpoint.name,
                                    "responses_json", json.dumps(responses, ensure_ascii=False),
                                    update_modified=False)
        if service.version == "1.0.0":
            frappe.db.set_value("API Documentation Service", service.name, "version", "2.0.0",
                                update_modified=False)


def unwrap_success_contract(responses):
    changed = False
    for code, response in responses.items():
        if not str(code).startswith("2"):
            continue
        for media in response.get("content", {}).values():
            schema = media.get("schema", {})
            if "message" not in schema.get("properties", {}):
                continue
            media["schema"] = schema["properties"]["message"]
            changed = True
            _unwrap_example(media, "example")
            for example in media.get("examples", {}).values():
                _unwrap_example(example, "value")
    return changed


def _unwrap_example(container, key):
    value = container.get(key)
    if isinstance(value, dict) and "message" in value:
        container[key] = value["message"]
        return True
    return False
