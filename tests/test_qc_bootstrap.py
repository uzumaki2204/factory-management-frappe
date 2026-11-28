"""Tests for the QC bootstrap catalog version contract."""

import importlib.util
import sys
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))


class Row(dict):
    __getattr__ = dict.__getitem__


def load_api():
    import factory_management

    def whitelist(**_kwargs):
        return lambda function: function

    frappe = types.SimpleNamespace(
        whitelist=whitelist,
        ValidationError=type("ValidationError", (Exception,), {}),
        PermissionError=type("PermissionError", (Exception,), {}),
        DoesNotExistError=type("DoesNotExistError", (Exception,), {}),
    )
    dependencies = {
        "device_registry": types.ModuleType("factory_management.device_registry"),
        "data_epoch": types.ModuleType("factory_management.data_epoch"),
        "api_access": types.ModuleType("factory_management.api_access"),
        "i18n": types.ModuleType("factory_management.i18n"),
    }
    dependencies["device_registry"].DEVICE_TYPE = "Factory Device"
    dependencies["data_epoch"].current = lambda: {}
    dependencies["api_access"].require_report_access = lambda _operation: None
    dependencies["i18n"].message = lambda key: key

    replacements = {"frappe": frappe}
    replacements.update({module.__name__: module for module in dependencies.values()})
    with ExitStack() as stack:
        stack.enter_context(patch.dict(sys.modules, replacements))
        for name, module in dependencies.items():
            stack.enter_context(patch.object(factory_management, name, module, create=True))
        spec = importlib.util.spec_from_file_location(
            "factory_management._qc_bootstrap_test_api", ROOT / "factory_management" / "api.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class QcBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.api = load_api()
        self.rows = {
            "Product": [Row(name="p1", product_code="P1", product_name="Product One",
                            customer="c1", production_season="s1")],
        }
        self.api._approved_device = lambda _device_id: types.SimpleNamespace(company="company-1")
        self.api._rows = lambda doctype, _fields, _filters=None, _limit=20000: self.rows.get(doctype, [])
        self.api._clock = lambda: {"server_date_key": "2026-11-28", "server_now_utc": "2026-11-28T00:00:00+00:00"}

    def test_versioned_request_returns_compact_unchanged_result(self):
        full = self.api.bootstrap(id="device-1")
        self.assertIn("catalog", full)
        self.assertIn("products", full["catalog"])
        self.assertTrue(full["catalog_version"])

        unchanged = self.api.bootstrap(id="device-1", catalog_version=full["catalog_version"])

        self.assertTrue(unchanged["unchanged"])
        self.assertEqual(unchanged["catalog_version"], full["catalog_version"])
        self.assertNotIn("catalog", unchanged)
        self.assertEqual(unchanged["server_date_key"], full["server_date_key"])

    def test_changed_catalog_returns_full_payload_with_new_version(self):
        full = self.api.bootstrap(id="device-1")
        self.rows["Product"][0]["product_name"] = "Product Two"

        changed = self.api.bootstrap(id="device-1", catalog_version=full["catalog_version"])

        self.assertIn("catalog", changed)
        self.assertEqual(changed["catalog"]["products"][0]["name"], "Product Two")
        self.assertNotEqual(changed["catalog_version"], full["catalog_version"])


if __name__ == "__main__":
    unittest.main()
