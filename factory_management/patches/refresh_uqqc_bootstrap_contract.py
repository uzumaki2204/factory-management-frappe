"""Document the compact response of the existing UQQC bootstrap operation."""

import json

import frappe

from factory_management.uqqc.i18n import text


def execute():
    doctype = "API Documentation Endpoint"
    name = frappe.db.get_value(doctype, {"operation_id": "uqqc_bootstrap"}, "name")
    if not name:
        return
    record = frappe.db.get_value(doctype, name, ["description", "parameters_json"], as_dict=True)
    parameters = json.loads(record.parameters_json or "[]")
    values = {}
    if not any(parameter.get("name") == "catalogVersion" for parameter in parameters):
        parameters.append({"name": "catalogVersion", "in": "query", "required": False,
                           "schema": {"type": "string"}, "description": text("docs.bootstrap_version", "en")})
        values["parameters_json"] = json.dumps(parameters, ensure_ascii=False)
    if record.description == ("Requires a valid Factory Device ID. Defect and position groups are stored "
                              "in the UQQC catalog DocTypes; production masters remain shared."):
        values["description"] = text("docs.bootstrap_catalog", "en")
    if values:
        frappe.db.set_value(doctype, name, values, update_modified=False)
