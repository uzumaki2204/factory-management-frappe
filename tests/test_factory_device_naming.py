"""Guard UUID identity when Frappe clears name before script naming."""

import importlib.util
import json
import sys
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


class DeviceNamingTests(unittest.TestCase):
    def setUp(self):
        self.frappe = types.ModuleType("frappe")
        self.frappe.local = types.SimpleNamespace(lang="en")
        self.frappe.ValidationError = type("ValidationError", (Exception,), {})

        def throw(message, error):
            raise error(message)

        self.frappe.throw = throw
        path = Path(__file__).parents[1] / "factory_management" / "device_registry.py"
        spec = importlib.util.spec_from_file_location("device_naming_under_test", path)
        self.registry = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"frappe": self.frappe}):
            spec.loader.exec_module(self.registry)

    def name_device(self, name):
        device = types.SimpleNamespace(name=name, flags=types.SimpleNamespace())
        self.registry.before_naming(device)
        # Frappe resets name between before_naming and autoname for By script.
        device.name = None
        self.registry.autoname(device)
        return device.name

    def test_new_devices_receive_distinct_uuid4_ids(self):
        first, second = self.name_device(None), self.name_device(None)
        self.assertEqual(uuid.UUID(first).version, 4)
        self.assertEqual(uuid.UUID(second).version, 4)
        self.assertNotEqual(first, second)

    def test_supplied_uuid_is_preserved(self):
        identity = str(uuid.uuid4())
        self.assertEqual(self.name_device(identity), identity)

    def test_invalid_identity_is_rejected(self):
        with self.assertRaises(self.frappe.ValidationError):
            self.name_device("invalid")

    def test_snapshot_disables_prompt_and_requires_device_name(self):
        root = Path(__file__).parents[1] / "factory_management"
        snapshot = json.loads((root / "doctype_metadata/factory_device.json").read_text())
        metadata = snapshot["doctype"]
        self.assertEqual(metadata["autoname"], "")
        self.assertEqual(metadata["naming_rule"], "By script")
        name_field = next(field for field in metadata["fields"] if field["fieldname"] == "device_name")
        self.assertEqual(name_field["reqd"], 1)


if __name__ == "__main__":
    unittest.main()
