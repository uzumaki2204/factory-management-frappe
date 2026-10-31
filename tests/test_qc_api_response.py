"""QC success payloads are direct JSON; errors and other RPCs stay native."""

import copy
import gzip
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))


def load_module(name, frappe):
    spec = importlib.util.spec_from_file_location(name, ROOT / "factory_management" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"frappe": frappe}):
        spec.loader.exec_module(module)
    return module


class Response:
    def __init__(self, payload, status=200, is_json=True):
        self.data = json.dumps(payload, ensure_ascii=False)
        self.status_code = status
        self.is_json = is_json
        self.headers = {"Set-Cookie": "sid=existing", "X-Test": "preserved"}

    def get_json(self, silent=False):
        return json.loads(self.data)

    def set_data(self, value):
        self.data = value

    def get_data(self):
        return self.data.encode("utf-8") if isinstance(self.data, str) else self.data


class QcResponseTests(unittest.TestCase):
    def setUp(self):
        self.frappe = types.SimpleNamespace(as_json=lambda value: json.dumps(value, ensure_ascii=False),
                                            form_dict={})
        context = patch.dict(sys.modules, {"frappe": self.frappe})
        context.start()
        self.addCleanup(context.stop)
        self.module = load_module("api_response", self.frappe)

    def apply(self, response, path):
        self.module.direct_qc_response(response, types.SimpleNamespace(path=path))
        return response.get_json()

    def test_all_business_modules_and_aliases_return_direct_data(self):
        from factory_management.uqqc.access import OPERATIONS

        methods = ["qc-inspection-summary", "factory_management.api.data_epoch",
                   "factory_management.api.sync_events", "factory_management.api.report_detail",
                   "factory_management.qc_reports.inspection_summary",
                   "factory_management.qcbrother_reports.inspection_summary",
                   "factory_management.qcbrother_reports.inspection_aggregate",
                   "factory_management.uqqc.api.dispatch"]
        methods += [alias for _, alias in OPERATIONS.values()]
        for method in methods:
            for data in ([], {}, [{"code": "Áo"}], {"acceptedLocalEventIds": ["offline-1"]},
                         {"message": "business field"}):
                with self.subTest(method=method, data=data):
                    response = Response({"message": data})
                    self.assertEqual(self.apply(response, "/api/method/" + method), data)
                    self.assertEqual(response.headers["Set-Cookie"], "sid=existing")
                    self.assertEqual(response.status_code, 200)

    def test_errors_downloads_unrelated_rpc_and_already_direct_payloads_are_unchanged(self):
        qc = "/api/method/factory_management.api.snapshot"
        cases = [(Response({"message": "forbidden"}, 403), qc),
                 (Response({"message": "retry", "exc_type": "UQQCSyncRetryError"}, 409), qc),
                 (Response({"message": "failed", "exception": "ValidationError"}), qc),
                 (Response({"message": "download"}, is_json=False), qc),
                 (Response({"message": {"paths": {}}}), "/api/method/factory_management.api_docs.openapi"),
                 (Response({"message": []}), "/api/method/frappe.client.get_list"),
                 (Response({"message": {}}), "/api/method/factory_management.spl_po.api.settings"),
                 (Response({"message": {}}), "/api/resource/Factory Device"),
                 (Response({"generation": "current"}), qc), (Response([]), qc)]
        self.frappe.form_dict["cmd"] = "factory_management.api.snapshot"
        for response, path in cases:
            before = response.data
            self.apply(response, path)
            self.assertEqual(response.data, before, path)

    def test_v1_and_legacy_rpc_paths(self):
        for path in ("/api/v1/method/factory_management.api.bootstrap", "/api/method", "/"):
            self.frappe.form_dict["cmd"] = "factory_management.api.bootstrap"
            self.assertEqual(self.apply(Response({"message": {"ready": True}}), path), {"ready": True})

    def test_large_uqqc_bootstrap_uses_gzip_only_when_requested(self):
        payload = {"catalogVersion": "version-1", "defectPositions": [
            {"id": str(index), "name": "Vị trí lỗi " + str(index)} for index in range(100)]}
        response = Response({"message": payload})
        request = types.SimpleNamespace(path="/api/method/uqqc-bootstrap",
                                        accept_encodings=types.SimpleNamespace(quality=lambda name: 1))
        self.module.direct_qc_response(response, request)
        self.assertEqual(response.headers["Content-Encoding"], "gzip")
        self.assertEqual(response.headers["Vary"], "Accept-Encoding")
        self.assertEqual(json.loads(gzip.decompress(response.data)), payload)
        self.assertLess(len(response.data), len(json.dumps(payload).encode("utf-8")))

        compact = Response({"message": {"catalogVersion": "version-1", "unchanged": True}})
        self.module.direct_qc_response(compact, request)
        self.assertNotIn("Content-Encoding", compact.headers)
        self.assertEqual(json.loads(compact.data)["unchanged"], True)

        not_accepted = Response({"message": payload})
        request.accept_encodings.quality = lambda name: 0
        self.module.direct_qc_response(not_accepted, request)
        self.assertNotIn("Content-Encoding", not_accepted.headers)


class ContractMigrationTests(unittest.TestCase):
    def test_existing_records_only_change_success_contract_and_default_service_version(self):
        endpoints = [types.SimpleNamespace(name="report", path="/api/method/factory_management.api.report_detail",
                     responses_json=json.dumps({"200": {"content": {"application/json": {"schema": {
                         "type": "object", "properties": {"message": {"type": "array", "items": {"type": "object"}}},
                     }}}}})),
                     types.SimpleNamespace(name="other", path="/api/method/frappe.client.get_list", responses_json="{}")]
        services = [types.SimpleNamespace(name="qc", version="1.0.0"),
                    types.SimpleNamespace(name="uqqc", version="custom")]
        writes = []

        def get_all(doctype, **kwargs):
            return services if doctype == "API Documentation Service" else endpoints if kwargs["filters"]["service"] == "qc" else []

        def set_value(doctype, name, field, value, **kwargs):
            writes.append((doctype, name, field))
            record = next(row for row in services + endpoints if row.name == name)
            setattr(record, field, value)

        module = load_module("api_contracts", types.SimpleNamespace(get_all=get_all,
                             db=types.SimpleNamespace(set_value=set_value)))
        module.migrate_success_contracts()
        self.assertEqual(writes, [("API Documentation Endpoint", "report", "responses_json"),
                                  ("API Documentation Service", "qc", "version")])
        self.assertEqual(services[1].version, "custom")
        writes.clear()
        module.migrate_success_contracts()
        self.assertEqual(writes, [])

    def test_migration_preserves_row_schema_customizations_errors_and_business_message(self):
        module = load_module("api_contracts", types.SimpleNamespace())
        rows = {"type": "array", "items": {"type": "object", "properties": {"customCode": {"type": "string"}}}}
        data = [{"customCode": "Áo", "message": "business field"}]
        responses = {"200": {"description": "Edited in Desk", "headers": {"X-Custom": {}}, "content": {
            "application/json": {"schema": {"type": "object", "required": ["message"],
                                             "properties": {"message": rows}},
                                 "example": {"message": data},
                                 "examples": {"empty": {"summary": "Custom", "value": {"message": []}}}},
        }}, "403": {"content": {"application/json": {"schema": {"properties": {"message": {"type": "string"}}}}}}}
        forbidden = copy.deepcopy(responses["403"])
        self.assertTrue(module.unwrap_success_contract(responses))
        media = responses["200"]["content"]["application/json"]
        self.assertEqual(media["schema"], rows)
        self.assertEqual(media["example"], data)
        self.assertEqual(media["examples"]["empty"], {"summary": "Custom", "value": []})
        self.assertEqual(responses["200"]["description"], "Edited in Desk")
        self.assertEqual(responses["200"]["headers"], {"X-Custom": {}})
        self.assertEqual(responses["403"], forbidden)
        before = copy.deepcopy(responses)
        self.assertFalse(module.unwrap_success_contract(responses))
        self.assertEqual(responses, before)


if __name__ == "__main__":
    unittest.main()
