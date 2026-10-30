"""The editable Desk catalog must stay aligned with the public row contracts."""

import csv
import importlib
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))


class CatalogTests(unittest.TestCase):
    def test_catalog_seeds_translated_contracts_once_and_preserves_desk_edits(self):
        records = {}
        frappe = types.ModuleType("frappe")
        frappe._ = lambda key: key
        frappe.whitelist = lambda **kwargs: lambda function: function
        frappe.db = types.SimpleNamespace(exists=lambda doctype, filters: filters["operation_id"] in records)

        def get_doc(values):
            def insert(**kwargs):
                records[values["operation_id"]] = values
            return types.SimpleNamespace(insert=insert)

        frappe.get_doc = get_doc
        with patch.dict(sys.modules, {"frappe": frappe}):
            access = importlib.import_module("factory_management.api_access")
            catalog = importlib.import_module("factory_management.qcbrother_reporting.catalog")
            catalog.seed_contracts("qc-service")
            summary = records["qcBrotherInspectionSummary"]
            summary["summary"] = "Edited in Desk"
            catalog.seed_contracts("qc-service")
        self.assertEqual(len(records), 2)
        self.assertEqual(summary["summary"], "Edited in Desk")
        for operation, record in records.items():
            self.assertEqual(record["path"], access.REPORT_ROUTES[operation])
            self.assertEqual(record["allowed_roles"], [{"role": "QC Report Reader"}])
            self.assertEqual(record["http_method"], "GET")
        aggregate = json.loads(records["qcBrotherInspectionAggregate"]["responses_json"])
        fields = aggregate["200"]["content"]["application/json"]["schema"]["items"]["properties"]
        self.assertIn("serialNo", fields)
        self.assertIn("totalPass", fields)
        self.assertNotIn("lineCode", fields)
        self.assertNotIn("eventNo", fields)
        self.assertEqual(set(aggregate), {"200", "400", "401", "403", "503"})
        keys = set()
        for kind, days in (("summary", 7), ("aggregate", 31)):
            contract = catalog.report_contract(kind, days)
            self._message_keys(contract, keys)
            keys.update((f"QCBROTHER_{kind.upper()}_TITLE", f"QCBROTHER_{kind.upper()}_DESCRIPTION", "QCBROTHER_REPORTS_TAG"))
        for language in ("en", "vi"):
            with (ROOT / f"factory_management/translations/{language}.csv").open(encoding="utf-8", newline="") as stream:
                translations = {row[0]: row[1] for row in csv.reader(stream) if len(row) >= 2}
            self.assertFalse(keys - translations.keys(), language)

    def test_summary_contract_refresh_updates_stock_values_only(self):
        frappe = types.ModuleType("frappe")
        frappe._ = lambda key: key
        frappe.whitelist = lambda **kwargs: lambda function: function
        with patch.dict(sys.modules, {"frappe": frappe}):
            catalog = importlib.import_module("factory_management.qcbrother_reporting.catalog")

        contract = catalog.report_contract("summary", 7)
        parameters = contract["parameters"]
        responses = contract["responses"]
        for parameter in parameters:
            if parameter["name"] in ("companyCode", "qc"):
                parameter["description"] = "QCBROTHER_FILTER_" + parameter["name"].upper()
        media = responses["200"]["content"]["application/json"]
        media["example"] = []
        responses["503"]["description"] = "QCBROTHER_SQL_UNAVAILABLE"
        values = {"parameters_json": json.dumps(parameters), "responses_json": json.dumps(responses)}
        writes = []

        def get_value(_doctype, key, _fields, as_dict=False):
            return types.SimpleNamespace(**values) if as_dict else "summary-endpoint"

        def set_value(_doctype, _name, updates, update_modified=False):
            writes.append(updates)
            values.update(updates)

        frappe.db = types.SimpleNamespace(get_value=get_value, set_value=set_value)
        with patch.object(catalog, "frappe", frappe):
            catalog.refresh_summary_contract()
            catalog.refresh_summary_contract()
        self.assertEqual(len(writes), 1)
        updated = json.loads(values["responses_json"])
        self.assertEqual(updated["503"]["description"], "QCBROTHER_UQQC_UNAVAILABLE")
        self.assertEqual(updated["200"]["content"]["application/json"]["example"][0]["eventNo"], "")
        self.assertEqual(updated["200"]["content"]["application/json"]["example"][1]["eventNo"], "PASS")

    def test_aggregate_contract_refresh_updates_stock_values_only(self):
        frappe = types.ModuleType("frappe")
        frappe._ = lambda key: key
        frappe.whitelist = lambda **kwargs: lambda function: function
        with patch.dict(sys.modules, {"frappe": frappe}):
            catalog = importlib.import_module("factory_management.qcbrother_reporting.catalog")
        contract = catalog.report_contract("aggregate", 31)
        parameters, responses = contract["parameters"], contract["responses"]
        next(item for item in parameters if item["name"] == "companyId")["description"] = "QCBROTHER_FILTER_COMPANYID"
        responses["200"]["content"]["application/json"]["example"] = []
        responses["503"]["description"] = "QCBROTHER_SQL_UNAVAILABLE"
        values = {"parameters_json": json.dumps(parameters), "responses_json": json.dumps(responses)}
        writes = []

        def get_value(_doctype, key, _fields, as_dict=False):
            return types.SimpleNamespace(**values) if as_dict else "aggregate-endpoint"

        def set_value(_doctype, _name, updates, update_modified=False):
            writes.append(updates)
            values.update(updates)

        frappe.db = types.SimpleNamespace(get_value=get_value, set_value=set_value)
        with patch.object(catalog, "frappe", frappe):
            catalog.refresh_aggregate_contract()
            catalog.refresh_aggregate_contract()
        self.assertEqual(len(writes), 1)
        updated = json.loads(values["responses_json"])
        self.assertEqual(updated["503"]["description"], "QCBROTHER_UQQC_UNAVAILABLE")
        self.assertEqual(updated["200"]["content"]["application/json"]["example"][0]["pass"], 2)
        self.assertEqual(json.loads(values["parameters_json"])[2]["description"],
                         "QCBROTHER_AGGREGATE_FILTER_COMPANYID")

    @classmethod
    def _message_keys(cls, value, keys):
        if isinstance(value, dict):
            for item in value.values():
                cls._message_keys(item, keys)
        elif isinstance(value, list):
            for item in value:
                cls._message_keys(item, keys)
        elif isinstance(value, str) and value.startswith(("QCBROTHER_", "QC_REPORT_")):
            keys.add(value)


if __name__ == "__main__":
    unittest.main()
