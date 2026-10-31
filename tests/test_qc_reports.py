"""Contract cases for the native Frappe QC report compatible with .NET."""

import importlib.util
import json
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))


def load_module(module_name, file_path, modules):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class ValidationError(Exception):
    pass


class FakeDb:
    def __init__(self):
        self.rows = [{
            "eventType": "DEFECT",
            "entityType": "QCInspection",
            "occurredDate": date(2026, 5, 3),
            "deviceName": "001QC1KT2",
            "quantitySummary": 12,
        }]
        self.query = None
        self.params = None

    def sql(self, query, params, as_dict=False):
        self.query = query
        self.params = params
        return self.rows


def fake_frappe(db=None):
    frappe = types.ModuleType("frappe")
    frappe._ = lambda value: value
    frappe.ValidationError = ValidationError
    frappe.PermissionError = PermissionError
    frappe.form_dict = {}
    frappe.db = db or FakeDb()
    frappe.utils = types.SimpleNamespace(getdate=lambda value: date.fromisoformat(str(value)))

    def whitelist(**_kwargs):
        return lambda function: function

    def throw(message, error_type):
        raise error_type(message)

    frappe.whitelist = whitelist
    frappe.throw = throw
    return frappe


class QCReportTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self.frappe = fake_frappe(self.db)
        self.access = types.ModuleType("factory_management.api_access")
        self.access.require_report_access = Mock()
        self.module = load_module(
            "qc_reports_under_test",
            ROOT / "factory_management" / "qc_reports.py",
            {"frappe": self.frappe, "factory_management.api_access": self.access},
        )

    def test_summary_matches_dotnet_filters_grouping_and_direct_row_shape(self):
        rows = self.module.inspection_summary(
            OccurredDateFrom="2026-05-07",
            OccurredDateTo="2026-05-01",
            EventType=" DEFECT ",
            EntityType="QCInsp",
            DeviceName=" 001QC1 ",
            DeviceNo="001",
            DeviceQc="QC1",
            CompaniesCode="KT",
            ProductsName="T-Shirt",
            QuantitySummary="12",
        )

        self.access.require_report_access.assert_called_once_with("qcInspectionSummaryNative")
        self.assertEqual(self.db.params["date_from"], "2026-05-01")
        self.assertEqual(self.db.params["date_to"], "2026-05-07")
        self.assertEqual(self.db.params["eventType"], "%DEFECT%")
        self.assertEqual(self.db.params["deviceName"], "%001QC1%")
        self.assertEqual(self.db.params["deviceNo"], "001%")
        self.assertEqual(self.db.params["deviceQc"], "QC1%")
        self.assertEqual(self.db.params["companiesCode"], "KT%")
        self.assertEqual(self.db.params["productsName"], "%T-Shirt%")
        self.assertEqual(self.db.params["entity_type_value"], "QCInspection")
        self.assertEqual(self.db.params["entity_type_filter"], "%QCInsp%")
        self.assertEqual(self.db.params["quantity_summary"], 12)
        self.assertIn("SUM(e.quantity_delta)", self.db.query)
        self.assertIn("LEFT JOIN `tabLine Group Assignment`", self.db.query)
        self.assertIn("ORDER BY occurredDate DESC", self.db.query)
        self.assertEqual(rows[0]["occurredDate"], "2026-05-03T00:00:00")
        self.assertEqual(rows[0]["entityType"], "QCInspection")

    def test_required_and_maximum_date_range_validation(self):
        self.db.sql = Mock()
        cases = (
            ({"OccurredDateFrom": "2026-05-01"}, "QC_REPORT_DATES_REQUIRED"),
            ({"OccurredDateFrom": "bad", "OccurredDateTo": "2026-05-01"}, "QC_REPORT_INVALID_DATE"),
            ({"OccurredDateFrom": "2026-05-01", "OccurredDateTo": "2026-05-08"},
             "QC_REPORT_RANGE_TOO_LONG"),
        )
        for arguments, expected in cases:
            with self.subTest(arguments=arguments), self.assertRaisesRegex(ValidationError, expected):
                self.module.inspection_summary(**arguments)
        self.db.sql.assert_not_called()

    def test_invalid_quantity_is_rejected_before_query(self):
        with self.assertRaisesRegex(ValidationError, "QC_REPORT_INVALID_QUANTITY"):
            self.module.inspection_summary(
                OccurredDateFrom="2026-05-01", OccurredDateTo="2026-05-01", QuantitySummary="2147483648"
            )
        self.assertIsNone(self.db.query)

    def test_empty_and_long_filters_follow_dotnet_normalization(self):
        self.module.inspection_summary(
            OccurredDateFrom="2026-05-01", OccurredDateTo="2026-05-01",
            DeviceName="  ", EventType="x" * 510,
        )
        self.assertNotIn("deviceName", self.db.params)
        self.assertEqual(self.db.params["eventType"], "%" + ("x" * 500) + "%")


class QCReportContractTests(unittest.TestCase):
    def test_native_contract_is_seeded_with_dotnet_names_roles_and_direct_array(self):
        frappe = fake_frappe()
        frappe.db.exists = Mock(return_value=False)
        captured = {}

        class Doc:
            def __init__(self, values):
                self.values = values

            def insert(self, ignore_permissions=False):
                captured["values"] = self.values
                captured["ignore_permissions"] = ignore_permissions
                return self

        frappe.get_doc = lambda values: Doc(values)
        access = types.ModuleType("factory_management.api_access")
        access.ENDPOINT_ROLE_TYPE = "API Documentation Endpoint Role"
        access.READER_ROLE = "QC Report Reader"
        access.REPORT_ROUTES = {"qcInspectionSummaryNative": "/api/method/factory_management.qc_reports.inspection_summary"}
        module = load_module(
            "api_docs_under_test",
            ROOT / "factory_management" / "api_docs.py",
            {"frappe": frappe, "factory_management.api_access": access},
        )

        module._seed_native_qc_summary_contract("qc-service")
        contract = captured["values"]
        params = json.loads(contract["parameters_json"])
        responses = json.loads(contract["responses_json"])
        names = {parameter["name"] for parameter in params}
        schema = responses["200"]["content"]["application/json"]["schema"]
        properties = schema["items"]["properties"]

        self.assertEqual(contract["operation_id"], "qcInspectionSummaryNative")
        self.assertEqual(contract["path"], "/api/method/factory_management.qc_reports.inspection_summary")
        self.assertEqual(contract["allowed_roles"], [{"role": "QC Report Reader"}])
        self.assertTrue({"OccurredDateFrom", "OccurredDateTo", "EntityType", "QuantitySummary"}.issubset(names))
        self.assertEqual(schema["type"], "array")
        self.assertEqual(properties["entityType"]["const"], "QCInspection")
        self.assertEqual(properties["occurredDate"]["format"], "date-time")
        self.assertNotIn("message", schema.get("properties", {}))
        self.assertEqual(captured["ignore_permissions"], True)


if __name__ == "__main__":
    unittest.main()
