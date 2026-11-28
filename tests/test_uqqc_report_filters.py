"""Unit tests for factory_management.uqqc.report_filters.

Run with:
  python -m unittest tests.test_uqqc_report_filters -v
"""

import importlib.util
import inspect
import json
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).parents[1]


class ValidationError(Exception):
    pass


class PermissionError(Exception):
    pass


def _load_report_filters(user="test@example.com", roles=None, has_perm=False):
    frappe = types.ModuleType("frappe")
    frappe._ = lambda text: text
    frappe.ValidationError = ValidationError
    frappe.PermissionError = PermissionError
    frappe.session = types.SimpleNamespace(user=user)
    frappe.get_roles = MagicMock(return_value=roles if roles is not None else ["QC Report Reader"])
    frappe.has_permission = MagicMock(return_value=has_perm)
    frappe.get_list = MagicMock()

    def _throw(message, exc=ValidationError):
        raise (exc or ValidationError)(message)

    frappe.throw = MagicMock(side_effect=_throw)
    frappe.utils = types.SimpleNamespace(
        getdate=lambda raw: raw if isinstance(raw, date) else date.fromisoformat(str(raw))
    )
    frappe.db = MagicMock()
    frappe.db.sql = MagicMock(return_value=[])

    def _whitelist(**_kwargs):
        return lambda fn: fn

    frappe.whitelist = _whitelist

    spec = importlib.util.spec_from_file_location(
        "uqqc_report_filters_under_test",
        ROOT / "factory_management" / "uqqc" / "report_filters.py",
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"frappe": frappe}):
        spec.loader.exec_module(module)
    return module, frappe


class ReportFiltersTestCase(unittest.TestCase):
    def setUp(self):
        self.mod, self.frappe = _load_report_filters()


class TestRequireReportAccess(ReportFiltersTestCase):
    def test_guest_is_denied(self):
        mod, _ = _load_report_filters(user="Guest", roles=[])
        with self.assertRaises(PermissionError):
            mod._require_report_access()

    def test_empty_user_is_denied(self):
        mod, _ = _load_report_filters(user="", roles=[])
        with self.assertRaises(PermissionError):
            mod._require_report_access()

    def test_qc_report_reader_is_allowed(self):
        mod, _ = _load_report_filters(user="qc@factory.com", roles=["QC Report Reader"])
        mod._require_report_access()

    def test_system_manager_is_allowed(self):
        mod, _ = _load_report_filters(user="admin@factory.com", roles=["System Manager"])
        mod._require_report_access()

    def test_administrator_is_always_allowed(self):
        mod, _ = _load_report_filters(user="Administrator", roles=[])
        mod._require_report_access()

    def test_role_less_user_with_has_permission_is_allowed(self):
        mod, _ = _load_report_filters(user="viewer@factory.com", roles=["Viewer"], has_perm=True)
        mod._require_report_access()

    def test_role_less_user_without_has_permission_is_denied(self):
        mod, _ = _load_report_filters(user="nobody@factory.com", roles=["Viewer"], has_perm=False)
        with self.assertRaises(PermissionError):
            mod._require_report_access()


class TestWhitelistContracts(ReportFiltersTestCase):
    def test_whitelisted_endpoints_define_parameter_type_hints(self):
        for fn in (self.mod.get_filter_options, self.mod.run_report):
            sig = inspect.signature(fn)
            for name, param in sig.parameters.items():
                self.assertNotEqual(
                    param.annotation,
                    inspect.Parameter.empty,
                    f"{fn.__name__} parameter '{name}' must have a type annotation",
                )


class TestNormalizeReportType(ReportFiltersTestCase):
    def test_summary_is_valid(self):
        self.assertEqual(self.mod._normalize_report_type("summary"), "summary")

    def test_device_is_valid(self):
        self.assertEqual(self.mod._normalize_report_type("device"), "device")

    def test_whitespace_is_stripped(self):
        self.assertEqual(self.mod._normalize_report_type("  SUMMARY  "), "summary")

    def test_invalid_raises(self):
        with self.assertRaises(ValidationError):
            self.mod._normalize_report_type("unknown")

    def test_none_defaults_to_summary(self):
        self.assertEqual(self.mod._normalize_report_type(None), "summary")


class TestParseDateRange(ReportFiltersTestCase):
    def test_valid_range(self):
        start, end = self.mod._parse_date_range("2026-01-01", "2026-01-31")
        self.assertEqual((start, end), ("2026-01-01", "2026-01-31"))

    def test_same_day_is_valid(self):
        start, end = self.mod._parse_date_range("2026-11-28", "2026-11-28")
        self.assertEqual(start, end)

    def test_reversed_dates_raise(self):
        with self.assertRaises(ValidationError):
            self.mod._parse_date_range("2026-11-30", "2026-11-01")

    def test_invalid_date_format_raises(self):
        with self.assertRaises(ValidationError):
            self.mod._parse_date_range("not-a-date", "2026-11-28")

    def test_missing_from_raises(self):
        with self.assertRaises(ValidationError):
            self.mod._parse_date_range(None, "2026-11-28")

    def test_missing_to_raises(self):
        with self.assertRaises(ValidationError):
            self.mod._parse_date_range("2026-11-28", "")


class TestParseFilters(ReportFiltersTestCase):
    def _parse(self, raw, fields=("qc", "company", "product")):
        return self.mod._parse_filters(raw, fields)

    def test_json_string_multi_value(self):
        result = self._parse('{"qc": ["QC1", "QC2"], "company": ["ACME"]}')
        self.assertEqual(result["qc"], ("QC1", "QC2"))
        self.assertEqual(result["company"], ("ACME",))

    def test_dict_input(self):
        result = self._parse({"qc": ["QC1"], "product": ["P001", "P002"]})
        self.assertEqual(result["qc"], ("QC1",))
        self.assertEqual(result["product"], ("P001", "P002"))

    def test_single_string_value(self):
        result = self._parse({"company": "ACME"})
        self.assertEqual(result["company"], ("ACME",))

    def test_empty_string_is_ignored(self):
        result = self._parse({"qc": "", "company": "ACME"})
        self.assertNotIn("qc", result)
        self.assertIn("company", result)

    def test_disallowed_field_is_ignored(self):
        result = self._parse({"hacked": ["sql injection"]})
        self.assertNotIn("hacked", result)

    def test_null_input_returns_empty(self):
        self.assertEqual(self._parse(None), {})

    def test_invalid_json_string_returns_empty(self):
        self.assertEqual(self._parse("{bad json!!}"), {})

    def test_duplicate_values_are_deduplicated(self):
        result = self._parse({"qc": ["QC1", "QC1", "QC1"]})
        self.assertEqual(result["qc"], ("QC1",))


class TestInClauseAndNormalization(ReportFiltersTestCase):
    def test_in_clause_single_and_multiple_values(self):
        params = {}
        clause = self.mod._in_clause("e.market", "market", ("EU", "US", "JP"), params)
        self.assertTrue(clause.startswith("e.market IN ("))
        for i, expected in enumerate(("EU", "US", "JP")):
            key = f"market_{i}"
            self.assertIn(f"%({key})s", clause)
            self.assertEqual(params[key], expected)

    def test_normalize_values_variants(self):
        self.assertEqual(self.mod._normalize_values(["a", "b"]), ["a", "b"])
        self.assertEqual(self.mod._normalize_values("hello"), ["hello"])
        self.assertEqual(self.mod._normalize_values('["x", "y"]'), ["x", "y"])
        self.assertEqual(self.mod._normalize_values(None), [])
        self.assertEqual(self.mod._normalize_values("   "), [])
        self.assertEqual(self.mod._normalize_values(["  a  ", " b "]), ["a", "b"])


class TestFormatRows(ReportFiltersTestCase):
    def test_int_and_date_fields_formatted(self):
        rows = [{
            "occurredOn": date(2026, 1, 5),
            "pass": "12",
            "rework": None,
            "defect": 3.7,
            "inspected": 15,
            "defectRate": 20,
            "totalRework": 0,
            "totalPass": 12,
            "totalDefect": 3,
            "totalInspected": 15,
            "totalDefectRate": 20.0,
            "deviceQc": "QC1",
            "companyName": "ACME",
            "sampleCode": "P001",
        }]
        result = self.mod._format_rows(rows, self.mod.SUMMARY_COLUMNS)
        self.assertEqual(result[0]["pass"], 12)
        self.assertEqual(result[0]["rework"], 0)
        self.assertEqual(result[0]["defect"], 3)
        self.assertEqual(result[0]["defectRate"], 20.0)
        self.assertEqual(result[0]["occurredOn"], "2026-01-05")


class TestGetFilterOptions(ReportFiltersTestCase):
    def test_returns_all_time_rows_without_doctype_get_list(self):
        self.frappe.db.sql.return_value = [{"qc": "QC1", "companyId": "ACME"}]
        result = self.mod.get_filter_options("summary")
        self.assertEqual(result, {"rows": [{"qc": "QC1", "companyId": "ACME"}]})
        self.frappe.get_list.assert_not_called()
        sql = self.frappe.db.sql.call_args[0][0]
        self.assertIn("SELECT DISTINCT", sql)
        self.assertNotIn("occurred_at >=", sql)

    def test_device_filter_options_join_variant_tables(self):
        self.frappe.db.sql.return_value = []
        self.mod.get_filter_options("device")
        self.frappe.get_list.assert_not_called()
        sql = self.frappe.db.sql.call_args[0][0]
        for table in ("`tabFactory Device`", "`tabMarket`", "`tabProduct Color`", "`tabProductSize`"):
            self.assertIn(table, sql)

    def test_guest_cannot_get_options(self):
        mod, _ = _load_report_filters(user="Guest", roles=[])
        with self.assertRaises(PermissionError):
            mod.get_filter_options("summary")


class TestRunReport(ReportFiltersTestCase):
    def test_summary_returns_summary_columns_and_uses_utc7_boundaries(self):
        self.frappe.db.sql.return_value = [{
            "occurredOn": date(2026, 11, 28),
            "deviceQc": "QC1",
            "companyName": "ACME",
            "sampleCode": "P001",
            "pass": 10,
            "rework": 1,
            "defect": 0,
            "inspected": 10,
            "defectRate": 0.0,
            "totalRework": 1,
            "totalPass": 10,
            "totalDefect": 0,
            "totalInspected": 10,
            "totalDefectRate": 0.0,
        }]
        result = self.mod.run_report("2026-11-01", "2026-11-28", "summary", "{}")
        self.assertEqual(result["columns"], self.mod.SUMMARY_COLUMNS)
        sql, params = self.frappe.db.sql.call_args[0][:2]
        self.assertIn("INTERVAL 7 HOUR", sql)
        self.assertEqual(params["from_date"], "2026-11-01")
        self.assertEqual(params["to_date"], "2026-11-28")

    def test_device_returns_device_columns(self):
        self.frappe.db.sql.return_value = []
        result = self.mod.run_report("2026-11-01", "2026-11-28", "device", "{}")
        self.assertEqual(result["columns"], self.mod.DEVICE_COLUMNS)
        sql = self.frappe.db.sql.call_args[0][0]
        self.assertIn("ORDER BY company.company_name, occurredOn", sql)

    def test_multi_value_filter_applied_via_bound_parameters(self):
        self.mod.run_report(
            "2026-11-01",
            "2026-11-28",
            "summary",
            json.dumps({"company": ["ACME", "GLOBAL"], "qc": ["QC1", "QC2"]}),
        )
        sql, params = self.frappe.db.sql.call_args[0][:2]
        self.assertEqual(params["company_0"], "ACME")
        self.assertEqual(params["company_1"], "GLOBAL")
        self.assertEqual(params["qc_0"], "QC1")
        self.assertEqual(params["qc_1"], "QC2")
        self.assertIn("daily.deviceQc IN (%(qc_0)s, %(qc_1)s)", sql)

    def test_guest_cannot_run_report(self):
        mod, _ = _load_report_filters(user="Guest", roles=[])
        with self.assertRaises(PermissionError):
            mod.run_report("2026-11-01", "2026-11-28")

    def test_reversed_dates_raise_validation(self):
        with self.assertRaises(ValidationError):
            self.mod.run_report("2026-11-30", "2026-11-01")


if __name__ == "__main__":
    unittest.main()
