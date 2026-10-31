"""Device Link list filters resolve IDs and visible names for all linked DocTypes."""

import importlib.util
import json
import re
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "factory_management/uqqc/list_filters.py"


def load_module():
    frappe = types.ModuleType("frappe")
    frappe.local = types.SimpleNamespace(form_dict={})
    frappe.get_list = None

    def decorator(**_kwargs):
        return lambda function: function

    frappe.whitelist = decorator
    frappe.read_only = decorator

    reportview = types.ModuleType("frappe.desk.reportview")
    reportview.get = lambda: frappe.local.form_dict.copy()
    reportview.get_list = reportview.get
    reportview.get_count = reportview.get
    desk = types.ModuleType("frappe.desk")
    desk.reportview = reportview
    modules = {"frappe": frappe, "frappe.desk": desk, "frappe.desk.reportview": reportview}
    spec = importlib.util.spec_from_file_location("device_list_filters_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module, frappe


class DeviceListFilterTests(unittest.TestCase):
    def setUp(self):
        self.module, self.frappe = load_module()
        self.devices = [
            {"name": "uuid-1", "device_name": "001QC1KT2"},
            {"name": "uuid-2", "device_name": "002QC2KT2"},
            {"name": "uuid-3", "device_name": "Cutting"},
            {"name": "uuid-4", "device_name": "QC Duplicate"},
            {"name": "uuid-5", "device_name": "QC Duplicate"},
        ]
        self.calls = []
        self.frappe.get_list = self.get_list

    def get_list(self, doctype, filters, fields, order_by, start, page_length):
        self.calls.append((doctype, filters))
        assert doctype == "Factory Device"
        field, (operator, expected) = next(iter(filters.items()))
        rows = []
        for row in self.devices:
            actual = row[field]
            if operator == "in":
                matched = actual in expected
            elif operator == "like":
                pattern = ".*" + ".*".join(re.escape(part) for part in expected.split("%")) + ".*"
                matched = re.match(pattern, actual, re.IGNORECASE) is not None
            else:
                raise AssertionError(f"Unexpected lookup operator: {operator}")
            if matched:
                rows.append({"name": row["name"]})
        return rows[start:start + page_length]

    def rewrite(self, doctype, filters, key="filters"):
        self.frappe.local.form_dict = {"doctype": doctype, key: json.dumps(filters)}
        self.module._rewrite_device_filters()
        return json.loads(self.frappe.local.form_dict[key])

    def test_in_and_not_in_resolve_visible_names_and_document_ids(self):
        for doctype in self.module.DEVICE_LINK_DOCTYPES:
            with self.subTest(doctype=doctype):
                included = self.rewrite(doctype, [["device", "in", ["001QC1KT2", "uuid-3"]]])
                excluded = self.rewrite(doctype, [["device", "not in", ["001QC1KT2", "uuid-3"]]])
                self.assertEqual(included, [["device", "in", ["uuid-1", "uuid-3"]]])
                self.assertEqual(excluded, [["device", "not in", ["uuid-1", "uuid-3"]]])

    def test_includes_duplicate_display_names(self):
        rewritten = self.rewrite("QC Inspection Event", ["device", "in", ["QC Duplicate"]])
        self.assertEqual(rewritten, ["device", "in", ["uuid-4", "uuid-5"]])

    def test_like_and_not_like_keep_display_name_matching(self):
        included = self.rewrite("UQQC Inspection Event", [["device", "like", "%QC%"]])
        excluded = self.rewrite("QC Inspection Event", [["device", "not like", "%QC%"]])
        self.assertEqual(included, [["device", "in", ["uuid-1", "uuid-2", "uuid-4", "uuid-5"]]])
        self.assertEqual(excluded, [["device", "not in", ["uuid-1", "uuid-2", "uuid-4", "uuid-5"]]])

    def test_supports_doctype_qualified_and_dictionary_filters_in_or_filters(self):
        qualified = self.rewrite(
            "QC Favorite", [["QC Favorite", "device", "in", ["Cutting"]]], key="or_filters"
        )
        dictionary = self.rewrite("QC Favorite", {"device": ["not in", ["Cutting"]]})
        self.assertEqual(qualified, [["QC Favorite", "device", "in", ["uuid-3"]]])
        self.assertEqual(dictionary, {"device": ["not in", ["uuid-3"]]})

    def test_unknown_and_empty_values_have_safe_match_none_or_all_semantics(self):
        no_rows = self.rewrite("QC Inspection Event", ["device", "in", ["unknown"]])
        all_rows = self.rewrite("QC Inspection Event", ["device", "not in", ["unknown"]])
        empty = self.rewrite("UQQC Inspection Event", ["device", "in", []])
        self.assertEqual(no_rows, ["device", "=", self.module.NO_MATCHING_DEVICE])
        self.assertEqual(all_rows, ["device", "!=", self.module.NO_MATCHING_DEVICE])
        self.assertEqual(empty, ["device", "=", self.module.NO_MATCHING_DEVICE])

    def test_non_device_doctypes_are_untouched(self):
        filters = [["device", "in", ["001QC1KT2"]]]
        result = self.rewrite("Factory Device", filters)
        self.assertEqual(result, filters)
        self.assertEqual(self.calls, [])

    def test_lookup_results_are_cached_during_request(self):
        filter_data = ["device", "in", ["001QC1KT2"]]
        first = self.rewrite("QC Inspection Event", filter_data)
        call_count = len(self.calls)
        second = self.rewrite("QC Inspection Event", filter_data)
        self.assertEqual(first, second)
        self.assertEqual(len(self.calls), call_count)


if __name__ == "__main__":
    unittest.main()
